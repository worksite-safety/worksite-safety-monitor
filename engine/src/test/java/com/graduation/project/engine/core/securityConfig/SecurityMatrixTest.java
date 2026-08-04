package com.graduation.project.engine.core.securityConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowable;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.service.EventService;
import com.graduation.project.engine.user.repository.TokenRepository;
import com.graduation.project.engine.user.service.UserService;
import com.google.gson.Gson;
import io.jsonwebtoken.io.DecodingException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.logout.LogoutHandler;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * Characterization of the URL -> access-decision matrix produced by {@link SecurityConfiguration}.
 *
 * <p>{@code @WebMvcTest} plus an explicit {@code @Import} of the real security configuration, the
 * real {@link JwtAuthenticationFilter} and the real {@link JwtService}. Nothing outside the web
 * layer is loaded, so no broker, mail server or database is involved; every collaborator the
 * filter chain or the controllers need is a {@code @MockBean}.
 *
 * <p>{@link JwtService} is imported for real rather than mocked so that
 * {@link #bearerHeader_blowsUpTheFilterChain()} can pin what a real request carrying a token does
 * today. Every other test here sends no {@code Authorization} header, so the filter short-circuits
 * before touching it.
 *
 * <p>Two behaviours pinned here are known defects that later slices will change deliberately:
 * unauthenticated requests answer <b>403, not 401</b>, and {@code POST /mail/send/{mail}} is
 * <b>public</b> - an unauthenticated open mail relay.
 */
@WebMvcTest
@ActiveProfiles("test")
@Import({SecurityConfiguration.class, JwtAuthenticationFilter.class, JwtService.class})
class SecurityMatrixTest {

  @Autowired
  private MockMvc mockMvc;

  // Filter-chain collaborators that live outside the web layer.
  @MockBean
  private AuthenticationProvider authenticationProvider;
  @MockBean
  private LogoutHandler logoutHandler;
  @MockBean
  private UserDetailsService userDetailsService;

  // EngineApplication carries an explicit @EnableMongoRepositories, so the repository beans are
  // registered even in a @WebMvcTest slice - where MongoDataAutoConfiguration is NOT applied and
  // there is therefore no 'mongoTemplate' for them to wire to. Mocking all three replaces those
  // bean definitions outright, which is what keeps this test infrastructure-free.
  @MockBean
  private TokenRepository tokenRepository;
  @MockBean
  private com.graduation.project.engine.user.repository.UserRepository userRepository;
  @MockBean
  private com.graduation.project.engine.event.repository.EventRepository eventRepository;

  // Controller collaborators.
  @MockBean
  private EventService eventService;
  @MockBean
  private MailService mailService;
  @MockBean
  private UserService userService;

  // -------------------------------------------------------------------------------------------
  // Denied
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("secured endpoint, no token -> 403 (NOT 401) with the CustomAuthenticationEntryPoint body")
  void securedEndpointWithoutToken_returns403WithEntryPointBody() throws Exception {
    MvcResult result = mockMvc.perform(get("/event/all-events")).andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(403);
    // Set literally via HttpServletResponse.setContentType in CustomAuthenticationEntryPoint.
    assertThat(result.getResponse().getContentType()).isEqualTo("application/json;charset=UTF-8");

    // The body is a JSON ARRAY holding exactly one object - an odd shape, but it is the shape
    // the React client's 403 handling has been written against.
    List<?> body = new Gson().fromJson(result.getResponse().getContentAsString(), List.class);
    assertThat(body).hasSize(1);
    @SuppressWarnings("unchecked")
    Map<String, String> entry = (Map<String, String>) body.get(0);
    assertThat(entry.keySet())
        .containsExactlyInAnyOrder("code", "statusMessage", "message", "timestamp", "path");
    assertThat(entry.get("code")).isEqualTo("403");
    assertThat(entry.get("statusMessage")).isEqualTo("Forbidden");
    assertThat(entry.get("message")).isEqualTo("Access denied");
    assertThat(entry.get("path")).isEqualTo("/event/all-events");
    assertThat(entry.get("timestamp")).isNotBlank();
  }

  @ParameterizedTest(name = "{0} {1} -> 403")
  @CsvSource({
      "GET,  /event/all-events",
      "GET,  /event/countable-events/1/2",
      "GET,  /event/periodic-events/1/2",
      "GET,  /event/pie-chart-events/1/2",
      "GET,  /nothing/is/mapped/here",
  })
  @DisplayName("ADMIN_URLS and anything unmatched are denied outright without a token")
  void deniedWithoutToken(String method, String path) throws Exception {
    int status = mockMvc.perform(method.equals("GET") ? get(path) : post(path))
        .andReturn().getResponse().getStatus();

    // Note the last row: no controller maps /nothing/is/mapped/here, but .anyRequest()
    // .authenticated() still denies it BEFORE the DispatcherServlet, so it is 403 and not 404.
    assertThat(status).isEqualTo(403);
  }

  // -------------------------------------------------------------------------------------------
  // Permitted
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("POST /auth/login is public")
  void login_isPublic() throws Exception {
    int status = mockMvc.perform(post("/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"email\":\"a@b.com\",\"password\":\"pw\"}"))
        .andReturn().getResponse().getStatus();

    assertThat(status).isNotEqualTo(403);
    assertThat(status).isEqualTo(200);
  }

  @ParameterizedTest(name = "{0} is public")
  @CsvSource({
      "/docs",
      "/docs/swagger-ui.html",
      "/event/get_image/1700000000000",
  })
  @DisplayName("PUBLIC_URLS reach the dispatcher instead of being denied")
  void publicUrls_areNot403(String path) throws Exception {
    int status = mockMvc.perform(get(path)).andReturn().getResponse().getStatus();

    // Asserting "not 403" rather than a specific success code on purpose: whether these resolve
    // to 200 or 404 depends on springdoc's auto-configuration and on whether output_image.jpg
    // happens to exist under event.image.path. Reaching the dispatcher at all is what proves
    // permitAll - a secured URL is rejected by the AuthorizationFilter before it ever gets there.
    assertThat(status).isNotEqualTo(403);
  }

  @Test
  @DisplayName("the image endpoint is public AND unauthenticated - currently 404, the file is absent")
  void imageEndpoint_isPublic() throws Exception {
    int status = mockMvc.perform(get("/event/get_image/1700000000000"))
        .andReturn().getResponse().getStatus();

    assertThat(status).isEqualTo(404);
  }

  @Test
  @DisplayName("DEFECT PINNED: POST /mail/send/{mail} is public - an unauthenticated open mail relay")
  void mailSend_isCurrentlyAnOpenRelay() throws Exception {
    MvcResult result = mockMvc.perform(post("/mail/send/victim@example.com")).andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
    assertThat(result.getResponse().getContentAsString()).isEqualTo("Successfuly mail sended !!");

    // And it really does send: an anonymous caller can make the server mail any address it likes.
    // A later slice deletes this endpoint; this test pins that removal as intentional, not a
    // regression.
    verify(mailService).sendUrgentEventMail(any(), any(LocalDateTime.class), eq("0"));
  }

  @ParameterizedTest(name = "{0} is public")
  @CsvSource({
      "/auth/register",
      "/auth/forgot-password",
      "/auth/change-password",
  })
  @DisplayName("the remaining PUBLIC_URLS under /auth are not denied")
  void authPublicUrls_areNot403(String path) throws Exception {
    int status = mockMvc.perform(post(path)
            .contentType(MediaType.APPLICATION_JSON)
            .content("{}"))
        .andReturn().getResponse().getStatus();

    assertThat(status).isNotEqualTo(403);
  }

  // -------------------------------------------------------------------------------------------
  // The broken JWT secret, observed at the HTTP layer
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("DEFECT PINNED: ANY request with a Bearer header blows the filter chain up (broken secret)")
  void bearerHeader_blowsUpTheFilterChain() {
    // JwtAuthenticationFilter calls jwtService.extractUsername(jwt) for every Bearer request, and
    // JwtService cannot build its signing key (see JwtServiceTest). The exception escapes the
    // servlet filter chain, so @ControllerAdvice never sees it: in a real deployment this is a
    // bare 500 on every authenticated call, which is why nothing can be logged into today.
    Throwable thrown = catchThrowable(() -> mockMvc.perform(
        get("/event/all-events").header("Authorization", "Bearer any.jwt.value")));

    assertThat(thrown).isNotNull();
    assertThat(causalChainOf(thrown)).hasAtLeastOneElementOfType(DecodingException.class);
  }

  private static List<Throwable> causalChainOf(Throwable throwable) {
    java.util.List<Throwable> chain = new java.util.ArrayList<>();
    for (Throwable t = throwable; t != null && !chain.contains(t); t = t.getCause()) {
      chain.add(t);
    }
    return chain;
  }
}
