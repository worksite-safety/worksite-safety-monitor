package com.graduation.project.engine.core.securityConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.controller.EventController;
import com.graduation.project.engine.event.repository.EventRepository;
import com.graduation.project.engine.event.service.EventService;
import com.graduation.project.engine.user.controller.UserController;
import com.graduation.project.engine.user.repository.UserRepository;
import com.graduation.project.engine.user.repository.TokenRepository;
import com.graduation.project.engine.user.service.UserService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.logout.LogoutHandler;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.bind.annotation.CrossOrigin;

/**
 * Which origins may call this API from a browser.
 *
 * <h2>The defect</h2>
 *
 * <p>{@code @CrossOrigin} sat on {@link EventController} and {@link UserController} with no
 * attributes. Bare, that annotation means {@code allowedOrigins = "*"} and
 * {@code allowedMethods = }the mapped method: <b>every site on the internet was permitted to make
 * cross-origin calls to this API and read the responses</b>. There was nothing to configure and
 * nothing to review - the policy was two characters of annotation on a class, repeated.
 *
 * <p>{@link SecurityConfiguration} already called {@code .cors(Customizer.withDefaults())}. With no
 * {@code CorsConfigurationSource} bean present, Spring Security falls back to the
 * {@code HandlerMappingIntrospector}, which is exactly how the bare annotations were reaching the
 * filter chain. Supplying the bean is what takes the decision away from the annotations - which is
 * why they had to be DELETED as well as overridden, and why {@link #noControllerDeclaresItsOwnCors}
 * is here.
 *
 * <h2>What the preflight proves</h2>
 *
 * <p>A browser refuses a cross-origin response that does not carry
 * {@code Access-Control-Allow-Origin}. So the presence or absence of that ONE header on the
 * preflight is the whole access decision, and it is asserted directly rather than through a status
 * code: a rejected preflight and an unmapped URL can both be 403, but only one of them omits the
 * header.
 */
@WebMvcTest
@ActiveProfiles("test")
@Import({SecurityConfiguration.class, JwtAuthenticationFilter.class, JwtService.class})
class CorsPolicyTest {

  /** The single entry in {@code app.cors.allowed-origins} in {@code src/test/resources}. */
  private static final String CONFIGURED_ORIGIN = "http://localhost:3000";

  @Autowired
  private MockMvc mockMvc;

  // Same collaborators SecurityMatrixTest mocks, and for the same reasons - see its comments.
  @MockBean
  private AuthenticationProvider authenticationProvider;
  @MockBean
  private LogoutHandler logoutHandler;
  @MockBean
  private UserDetailsService userDetailsService;
  @MockBean
  private TokenRepository tokenRepository;
  @MockBean
  private UserRepository userRepository;
  @MockBean
  private EventRepository eventRepository;
  @MockBean
  private EventService eventService;
  @MockBean
  private MailService mailService;
  @MockBean
  private UserService userService;

  // -------------------------------------------------------------------------------------------
  // Allowed
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("preflight from the configured origin is answered with THAT origin, not '*'")
  void preflightFromConfiguredOrigin_isAllowed() throws Exception {
    MvcResult result = mockMvc.perform(options("/event/all-events")
            .header(HttpHeaders.ORIGIN, CONFIGURED_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
        .andReturn();

    // Echoing the specific origin rather than answering "*" is the observable difference between
    // "these origins are trusted" and "everyone is": a wildcard response is identical for the
    // frontend and for an attacker's page, so it cannot distinguish them.
    assertThat(result.getResponse().getHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
        .isEqualTo(CONFIGURED_ORIGIN);
  }

  @Test
  @DisplayName("preflight from the configured origin permits the Authorization header")
  void preflightFromConfiguredOrigin_permitsTheAuthorizationHeader() throws Exception {
    // Every authenticated call the frontend makes attaches `Authorization: Bearer ...` by hand
    // (web/src/util/axios.js has no request interceptor), and a non-simple header makes the
    // request preflighted. A policy that allowed the origin but not this header would break every
    // logged-in page while looking correct in a status code.
    MvcResult result = mockMvc.perform(options("/event/all-events")
            .header(HttpHeaders.ORIGIN, CONFIGURED_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization"))
        .andReturn();

    assertThat(result.getResponse().getHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
        .isEqualTo(CONFIGURED_ORIGIN);
    assertThat(result.getResponse().getHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS))
        .containsIgnoringCase("authorization");
  }

  @Test
  @DisplayName("an ACTUAL request from the configured origin is readable by the browser")
  void actualRequestFromConfiguredOrigin_carriesTheHeader() throws Exception {
    // The preflight tests above only prove the browser is allowed to SEND the request. The header
    // must be on the real response too, or the frontend makes the call successfully and then the
    // browser refuses to hand it the body. Deleting two @CrossOrigin annotations is exactly the
    // kind of change that could pass every preflight assertion and still break every page.
    MvcResult result = mockMvc.perform(get("/event/get_image/1700000000000")
            .header(HttpHeaders.ORIGIN, CONFIGURED_ORIGIN))
        .andReturn();

    assertThat(result.getResponse().getHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
        .isEqualTo(CONFIGURED_ORIGIN);
  }

  // -------------------------------------------------------------------------------------------
  // Denied
  // -------------------------------------------------------------------------------------------

  @ParameterizedTest(name = "preflight from {0} gets no Access-Control-Allow-Origin")
  @ValueSource(strings = {
      "http://evil.example.com",
      "https://evil.example.com",
      // The near-misses matter more than the obvious one: a substring, startsWith or endsWith
      // check would wave at least one of these through. Scheme and port are part of an origin -
      // https://localhost:3000 is a DIFFERENT origin from http://localhost:3000.
      "http://localhost.evil.example.com",
      "http://evil.example.com:3000",
      "http://localhost:3001",
      "https://localhost:3000",
  })
  @DisplayName("preflight from an unlisted origin is NOT granted")
  void preflightFromUnlistedOrigin_isDenied(String origin) throws Exception {
    MvcResult result = mockMvc.perform(options("/event/all-events")
            .header(HttpHeaders.ORIGIN, origin)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET"))
        .andReturn();

    assertThat(result.getResponse().getHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)).isNull();
  }

  @Test
  @DisplayName("a PUBLIC endpoint is not a CORS exemption either")
  void publicEndpointFromUnlistedOrigin_isDenied() throws Exception {
    // /event/get_image/** is in PUBLIC_URLS, so it needs no token. That makes it the one endpoint
    // where a wildcard CORS policy is directly exploitable: any page could read the worksite
    // camera frame. "Unauthenticated" must not imply "readable by any origin".
    MvcResult result = mockMvc.perform(get("/event/get_image/1700000000000")
            .header(HttpHeaders.ORIGIN, "http://evil.example.com"))
        .andReturn();

    assertThat(result.getResponse().getHeader(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN)).isNull();
  }

  // -------------------------------------------------------------------------------------------
  // ...and the annotations are gone, not merely overridden
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("no controller declares its own CORS policy via @CrossOrigin")
  void noControllerDeclaresItsOwnCors() {
    // Analogous to SecurityMatrixTest#mailControllerClassIsGone. Without this, re-adding a bare
    // @CrossOrigin would put a second, wide-open policy back in the codebase; the tests above
    // could still pass, because Spring Security's filter answers the preflight from the bean
    // before the annotation is ever consulted. One policy, in one place, is the property being
    // asserted - not just "the current answers are right".
    assertThat(EventController.class.getAnnotation(CrossOrigin.class)).isNull();
    assertThat(UserController.class.getAnnotation(CrossOrigin.class)).isNull();
  }
}
