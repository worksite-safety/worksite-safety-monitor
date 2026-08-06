package com.graduation.project.engine.core.securityConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.graduation.project.engine.email.service.MailService;
import com.graduation.project.engine.event.service.EventService;
import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.Token;
import com.graduation.project.engine.user.model.TokenType;
import com.graduation.project.engine.user.model.User;
import com.graduation.project.engine.user.repository.TokenRepository;
import com.graduation.project.engine.user.service.UserService;
import com.google.gson.Gson;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.io.Decoders;
import io.jsonwebtoken.security.Keys;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import javax.crypto.SecretKey;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
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
 * <p>{@link JwtService} is imported for real rather than mocked, and is signed with the throwaway
 * {@code jwt.secret} in {@code src/test/resources/application.yml}. That is what lets the
 * bearer-token tests below mint tokens the server genuinely accepts, backdate one to prove
 * expiry, and sign another with a foreign key to prove forgery is rejected - none of which a
 * mocked JwtService could show.
 *
 * <p>One behaviour pinned here is a known defect that a later slice will change deliberately:
 * unauthenticated requests answer <b>403, not 401</b>.
 *
 * <p>The open mail relay that used to be pinned here is gone: {@code MailController} - which let
 * any anonymous caller {@code POST /mail/send/{address}} and have the server mail that address -
 * has been deleted, and {@link #mailSend_relayEndpointIsDeleted()} now measures its absence.
 * {@code "/mail/**"} remains in {@code PUBLIC_URLS}, so the URL is still reachable and simply
 * resolves to nothing; removing that entry is a {@link SecurityConfiguration} change owned
 * elsewhere.
 */
@WebMvcTest
@ActiveProfiles("test")
@Import({SecurityConfiguration.class, JwtAuthenticationFilter.class, JwtService.class})
class SecurityMatrixTest {

  @Autowired
  private MockMvc mockMvc;

  /** The real bean, used to mint tokens the server will accept - not a hand-rolled equivalent. */
  @Autowired
  private JwtService jwtService;

  /** The same secret the JwtService bean was built with, so tests can forge and backdate. */
  @Value("${jwt.secret}")
  private String configuredSecret;

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
  @DisplayName("the open mail relay is GONE: POST /mail/send/{mail} maps to nothing and sends nothing")
  void mailSend_relayEndpointIsDeleted() throws Exception {
    MvcResult result = mockMvc.perform(post("/mail/send/victim@example.com")).andReturn();

    // INVERTED. This previously asserted 200 + "Successfuly mail sended !!" + a real
    // sendUrgentEventMail call, pinning MailController as an unauthenticated open mail relay:
    // any anonymous caller could make the server send mail to an address of their choosing, with
    // a hardcoded sender identity, as many times as they liked. The controller is deleted.
    //
    // The status is 403 because "/mail/**" has also been removed from PUBLIC_URLS, so the request
    // never reaches the DispatcherServlet. That alone would not prove the controller is gone --
    // securing a URL and deleting its handler look identical from out here -- so the class's
    // absence is asserted directly below. Both facts matter: the handler must not exist, AND no
    // stale permitAll entry may survive it.
    assertThat(result.getResponse().getStatus()).isEqualTo(403);
    assertThat(result.getResponse().getContentAsString()).doesNotContain("mail sended");

    // The whole point of the removal: no anonymous request can cause an outbound mail.
    verifyNoInteractions(mailService);
  }

  @Test
  @DisplayName("no MailController class remains on the classpath")
  void mailControllerClassIsGone() {
    // Proves the handler was deleted rather than merely made unreachable. Without this, restoring
    // the controller and a permitAll entry together would reopen the relay while the status
    // assertion above still passed on some other 403.
    assertThatThrownBy(
        () -> Class.forName("com.graduation.project.engine.email.controller.MailController"))
        .isInstanceOf(ClassNotFoundException.class);
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
  // Unusable tokens are REJECTED, not fatal
  // -------------------------------------------------------------------------------------------
  //
  // A token the server cannot verify is an ordinary authentication outcome, not a server fault.
  // Every case below must land on the same 403 an anonymous request gets, because the alternative
  // is a 500 raised INSIDE the servlet filter chain - outside DispatcherServlet, where
  // @ControllerAdvice can never reach it. A browser holding one stale token would then get a bare
  // 500 on every endpoint it touches, public ones included.

  @Test
  @DisplayName("expired token -> 403 with the entry point body, NOT 500")
  void expiredToken_isRejectedNotFatal() throws Exception {
    String expired = signedToken(appKey(), Instant.now().minus(2, ChronoUnit.HOURS),
        Instant.now().minus(1, ChronoUnit.HOURS));

    MvcResult result = mockMvc.perform(get("/event/all-events")
        .header("Authorization", "Bearer " + expired)).andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(403);
    assertEntryPointBody(result, "/event/all-events");
  }

  @Test
  @DisplayName("valid structure, wrong signing key -> 403, NOT 500")
  void wrongSignature_isRejectedNotFatal() throws Exception {
    // Correct three-part shape, unexpired, parses cleanly - and signed by someone else. This is
    // the forged-token case, and it must be indistinguishable from "no token" to the caller.
    SecretKey foreignKey = Keys.hmacShaKeyFor(Decoders.BASE64.decode(
        "d3Jvbmctc2lnbmF0dXJlLWtleS11c2VkLW9ubHktYnktdGhlLXNlY3VyaXR5LXRlc3RzLTAxMjM0NTY3ODk="));
    String forged = signedToken(foreignKey, Instant.now(), Instant.now().plus(1, ChronoUnit.HOURS));

    MvcResult result = mockMvc.perform(get("/event/all-events")
        .header("Authorization", "Bearer " + forged)).andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(403);
    assertEntryPointBody(result, "/event/all-events");
  }

  @ParameterizedTest(name = "garbage bearer value [{0}] -> 403")
  @ValueSource(strings = {
      "not-a-jwt",
      "a.b.c",
      "eyJhbGciOiJIUzI1NiJ9.this-half-is-not-base64.sig",
      "....",
      " ",
  })
  @DisplayName("malformed Authorization: Bearer values -> 403, NOT 500")
  void malformedBearerValue_isRejectedNotFatal(String garbage) throws Exception {
    int status = mockMvc.perform(get("/event/all-events")
            .header("Authorization", "Bearer " + garbage))
        .andReturn().getResponse().getStatus();

    assertThat(status).isEqualTo(403);
  }

  @Test
  @DisplayName("an empty Bearer value -> 403, NOT 500 (jjwt raises IllegalArgumentException here, not JwtException)")
  void emptyBearerValue_isRejectedNotFatal() throws Exception {
    // "Bearer " passes the startsWith check, so substring(7) hands jjwt an empty string. jjwt
    // answers with a plain IllegalArgumentException rather than a JwtException, so catching only
    // JwtException in the filter would still 500 on this one. Pinned separately for that reason.
    int status = mockMvc.perform(get("/event/all-events").header("Authorization", "Bearer "))
        .andReturn().getResponse().getStatus();

    assertThat(status).isEqualTo(403);
  }

  // -------------------------------------------------------------------------------------------
  // ...and a good token still gets in
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("a token this server issued authenticates and reaches the controller")
  void validToken_authenticates() throws Exception {
    // Without this test, "reject everything that does not parse" and "reject everything" pass the
    // same assertions, and the API would be exactly as unusable as before - only with a tidier
    // status code. This is the test that says the pipe is open.
    User admin = User.builder().id("u1").email("aziz@example.com").password("hashed")
        .role(Role.ADMIN).build();
    String token = jwtService.generateToken(admin);

    when(userDetailsService.loadUserByUsername("aziz@example.com")).thenReturn(admin);
    when(tokenRepository.findByToken(token))
        .thenReturn(Optional.of(Token.builder().token(token).user(admin)
            .tokenType(TokenType.BEARER).expired(false).revoked(false).build()));
    when(eventService.getAllEvents()).thenReturn(List.of());

    MvcResult result = mockMvc.perform(get("/event/all-events")
        .header("Authorization", "Bearer " + token)).andReturn();

    assertThat(result.getResponse().getStatus()).isEqualTo(200);
    assertThat(result.getResponse().getContentAsString()).isEqualTo("[]");
  }

  @Test
  @DisplayName("a revoked token is refused even though it verifies and has not expired")
  void revokedToken_isRefused() throws Exception {
    // The DB-side half of the check. Logout marks tokens revoked; the signature stays valid until
    // exp, so only tokenRepository can tell the difference.
    User admin = User.builder().id("u1").email("aziz@example.com").password("hashed")
        .role(Role.ADMIN).build();
    String token = jwtService.generateToken(admin);

    when(userDetailsService.loadUserByUsername("aziz@example.com")).thenReturn(admin);
    when(tokenRepository.findByToken(token))
        .thenReturn(Optional.of(Token.builder().token(token).user(admin)
            .tokenType(TokenType.BEARER).expired(false).revoked(true).build()));

    int status = mockMvc.perform(get("/event/all-events")
        .header("Authorization", "Bearer " + token)).andReturn().getResponse().getStatus();

    assertThat(status).isEqualTo(403);
  }

  // -------------------------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------------------------

  /** The key the application itself is configured with, read from src/test/resources. */
  private SecretKey appKey() {
    return Keys.hmacShaKeyFor(Decoders.BASE64.decode(configuredSecret));
  }

  private static String signedToken(SecretKey key, Instant issuedAt, Instant expiresAt) {
    return Jwts.builder()
        .subject("aziz@example.com")
        .claim("authorities", List.of(Map.of("authority", "ADMIN")))
        .issuedAt(Date.from(issuedAt))
        .expiration(Date.from(expiresAt))
        .signWith(key, Jwts.SIG.HS256)
        .compact();
  }

  private static void assertEntryPointBody(MvcResult result, String path) throws Exception {
    assertThat(result.getResponse().getContentType()).isEqualTo("application/json;charset=UTF-8");
    List<?> body = new Gson().fromJson(result.getResponse().getContentAsString(), List.class);
    assertThat(body).hasSize(1);
    @SuppressWarnings("unchecked")
    Map<String, String> entry = (Map<String, String>) body.get(0);
    assertThat(entry.get("code")).isEqualTo("403");
    assertThat(entry.get("statusMessage")).isEqualTo("Forbidden");
    assertThat(entry.get("message")).isEqualTo("Access denied");
    assertThat(entry.get("path")).isEqualTo(path);
  }
}
