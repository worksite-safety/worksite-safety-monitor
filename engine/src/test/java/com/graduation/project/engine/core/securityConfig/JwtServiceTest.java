package com.graduation.project.engine.core.securityConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.ExpiredJwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.MalformedJwtException;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.io.Decoders;
import io.jsonwebtoken.security.Keys;
import io.jsonwebtoken.security.SignatureException;
import io.jsonwebtoken.security.WeakKeyException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;

/**
 * Unit tests for {@link JwtService}.
 *
 * <p>This class used to be a characterization suite that pinned the OPPOSITE of everything below:
 * {@code SECRET_KEY} was the literal string {@code "${JWT_SECRET}"} left behind by a history
 * rewrite, so {@code Decoders.BASE64.decode(...)} threw on the first line of {@code getSignInKey()}
 * and every public method on this class threw {@link io.jsonwebtoken.io.DecodingException} before
 * it looked at its arguments. Those assertions have been inverted, not deleted - each one now
 * asserts the behaviour the method was always meant to have.
 *
 * <p>The secret is a constructor argument now, which is what makes this class testable at all: a
 * {@code private static final String} is a compile-time constant, javac inlines it at the use site,
 * and neither {@code @Value} nor reflection can rebind it after the fact.
 *
 * <p>The exception-type tests near the bottom are not decoration. They are the contract
 * {@link JwtAuthenticationFilter} has to catch: a token that cannot be verified must become a 403,
 * and the filter can only do that if it knows precisely which throwables to expect - including the
 * one case where jjwt raises a bare {@link IllegalArgumentException} instead of a
 * {@link io.jsonwebtoken.JwtException}.
 */
class JwtServiceTest {

  /** Base64 of a 54-byte string; HS256 requires at least 32 bytes of key material. */
  private static final String SECRET =
      "dGVzdC1vbmx5LWp3dC1zaWduaW5nLWtleS1ub3QtYS1yZWFsLXNlY3JldC0wMTIzNDU2Nzg5";
  private static final long EXPIRY_MS = 1000L * 60 * 20;

  private final JwtService jwtService = new JwtService(SECRET, EXPIRY_MS);

  private static final UserDetails ADMIN = User.builder()
      .email("aziz@example.com")
      .password("irrelevant")
      .role(Role.ADMIN)
      .build();

  // -------------------------------------------------------------------------------------------
  // Round trip
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("generateToken then extractUsername round-trips the email")
  void generateToken_thenExtractUsername_roundTripsTheEmail() {
    String token = jwtService.generateToken(ADMIN);

    assertThat(jwtService.extractUsername(token)).isEqualTo("aziz@example.com");
  }

  @Test
  @DisplayName("generateToken(extraClaims, ...) carries the extra claims through the round trip")
  void generateTokenWithExtraClaims_carriesThemThrough() {
    String token = jwtService.generateToken(Map.of("k", "v"), ADMIN);

    // Bound to Object first: inlining this makes extractClaim's <T> inferable only from the
    // assertThat overload set, and Assertions.assertThat(Predicate) vs (IntPredicate) is ambiguous.
    Object extra = jwtService.extractClaim(token, claims -> claims.get("k"));
    assertThat(extra).isEqualTo("v");
    // setClaims() REPLACES the claim map, so the subject and authorities must survive being set
    // after it. They do, because generateToken sets them afterwards - worth pinning, since
    // reordering those builder calls would silently produce a subject-less token.
    assertThat(jwtService.extractUsername(token)).isEqualTo("aziz@example.com");
  }

  @Test
  @DisplayName("extractClaim applies the resolver to the parsed claims")
  void extractClaim_appliesTheResolver() {
    String token = jwtService.generateToken(ADMIN);

    assertThat(jwtService.extractClaim(token, Claims::getSubject)).isEqualTo("aziz@example.com");
  }

  @Test
  @DisplayName("isTokenValid is true for a fresh token belonging to that user")
  void isTokenValid_trueForOwnFreshToken() {
    assertThat(jwtService.isTokenValid(jwtService.generateToken(ADMIN), ADMIN)).isTrue();
  }

  @Test
  @DisplayName("isTokenValid is false when the subject is a different user")
  void isTokenValid_falseForSomeoneElsesToken() {
    UserDetails other = User.builder().email("someone.else@example.com")
        .password("irrelevant").role(Role.ADMIN).build();

    assertThat(jwtService.isTokenValid(jwtService.generateToken(ADMIN), other)).isFalse();
  }

  // -------------------------------------------------------------------------------------------
  // Expiry
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("exp - iat equals the configured expiry exactly")
  void expiryWindow_matchesTheConfiguredValue() {
    String token = jwtService.generateToken(ADMIN);

    Date issuedAt = jwtService.extractClaim(token, Claims::getIssuedAt);
    Date expiration = jwtService.extractClaim(token, Claims::getExpiration);

    // JWT iat/exp are whole seconds, so this can only be exact if generateToken reads the clock
    // ONCE. Reading System.currentTimeMillis() separately for iat and exp makes this assertion
    // fail roughly one run in a thousand, when the millisecond ticks between the two reads.
    assertThat(expiration.getTime() - issuedAt.getTime()).isEqualTo(EXPIRY_MS);
  }

  @Test
  @DisplayName("the expiry is configuration, not a literal: a different value produces a different window")
  void expiryWindow_isConfigurable() {
    JwtService fiveMinutes = new JwtService(SECRET, 1000L * 60 * 5);
    String token = fiveMinutes.generateToken(ADMIN);

    Date issuedAt = fiveMinutes.extractClaim(token, Claims::getIssuedAt);
    Date expiration = fiveMinutes.extractClaim(token, Claims::getExpiration);

    assertThat(expiration.getTime() - issuedAt.getTime()).isEqualTo(1000L * 60 * 5);
  }

  // -------------------------------------------------------------------------------------------
  // Claim shape
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("the authorities claim renders as [{\"authority\":\"ADMIN\"}] objects, not strings")
  void authoritiesClaimRendersAsObjects() {
    // This was a PROXY canary while token generation was unreachable: it rebuilt the jjwt chain
    // by hand against a throwaway key and asserted on THAT. It now asserts on a token JwtService
    // actually produced, so it pins the real wire format.
    //
    // Both JwtAuthenticationFilter's consumers and the React client read this claim. A Spring
    // Security or jjwt upgrade that starts serialising SimpleGrantedAuthority as a plain string
    // is a silent breaking change to every token already in circulation; this is the tripwire.
    String token = jwtService.generateToken(ADMIN);

    String payload = new String(Base64.getUrlDecoder().decode(token.split("\\.")[1]),
        StandardCharsets.UTF_8);
    assertThat(payload).contains("\"authorities\":[{\"authority\":\"ADMIN\"}]");
    assertThat(payload).contains("\"sub\":\"aziz@example.com\"");

    Object authorities = jwtService.extractClaim(token, claims -> claims.get("authorities"));
    assertThat(authorities).isInstanceOf(List.class);
    assertThat((List<?>) authorities)
        .singleElement()
        .isEqualTo(Map.of("authority", "ADMIN"));
  }

  // -------------------------------------------------------------------------------------------
  // What an unusable token throws - the contract JwtAuthenticationFilter must catch
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("an expired token throws ExpiredJwtException - isTokenValid never gets to return false")
  void expiredToken_throwsExpiredJwtException() {
    // Note this THROWS rather than returning false: jjwt rejects exp during parsing, so
    // isTokenValid's own !isTokenExpired() branch is unreachable for a genuinely expired token.
    // JwtAuthenticationFilter therefore cannot handle expiry with a boolean check alone.
    String expired = signedWith(appKey(), Instant.now().minus(2, ChronoUnit.HOURS),
        Instant.now().minus(1, ChronoUnit.HOURS));

    assertThatThrownBy(() -> jwtService.extractUsername(expired))
        .isInstanceOf(ExpiredJwtException.class);
    assertThatThrownBy(() -> jwtService.isTokenValid(expired, ADMIN))
        .isInstanceOf(ExpiredJwtException.class);
  }

  @Test
  @DisplayName("a token signed with another key throws SignatureException")
  void wrongSignature_throwsSignatureException() {
    Key foreign = Keys.hmacShaKeyFor(Decoders.BASE64.decode(
        "d3Jvbmctc2lnbmF0dXJlLWtleS11c2VkLW9ubHktYnktdGhlLXNlY3VyaXR5LXRlc3RzLTAxMjM0NTY3ODk="));
    String forged = signedWith(foreign, Instant.now(), Instant.now().plus(1, ChronoUnit.HOURS));

    assertThatThrownBy(() -> jwtService.extractUsername(forged))
        .isInstanceOf(SignatureException.class);
  }

  @Test
  @DisplayName("garbage throws MalformedJwtException")
  void garbageToken_throwsMalformedJwtException() {
    assertThatThrownBy(() -> jwtService.extractUsername("not-a-jwt"))
        .isInstanceOf(MalformedJwtException.class);
  }

  @Test
  @DisplayName("null/empty throws IllegalArgumentException, which is NOT a JwtException")
  void nullOrEmptyToken_throwsIllegalArgumentException() {
    // The old suite asserted DecodingException here, because the key blew up before the token was
    // ever looked at. Now the token IS looked at, and jjwt's null/empty guard is a plain
    // IllegalArgumentException that does NOT extend JwtException. A filter that catches only
    // JwtException still 500s on the header "Authorization: Bearer " with nothing after it.
    assertThatThrownBy(() -> jwtService.extractUsername(null))
        .isInstanceOf(IllegalArgumentException.class)
        .isNotInstanceOf(io.jsonwebtoken.JwtException.class);
    assertThatThrownBy(() -> jwtService.extractUsername(""))
        .isInstanceOf(IllegalArgumentException.class)
        .isNotInstanceOf(io.jsonwebtoken.JwtException.class);
  }

  // -------------------------------------------------------------------------------------------
  // Refuse to start rather than start insecure
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("a missing or blank secret fails construction, so the context fails to start")
  void blankSecret_failsFast() {
    // Spring resolves ${JWT_SECRET} before this constructor runs, so an ABSENT variable already
    // fails at placeholder resolution. This covers the next case down: the variable is present
    // but empty, which resolves fine and would otherwise produce a zero-length key.
    assertThatThrownBy(() -> new JwtService("", EXPIRY_MS))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("JWT_SECRET");
    assertThatThrownBy(() -> new JwtService("   ", EXPIRY_MS))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("JWT_SECRET");
  }

  @Test
  @DisplayName("a secret shorter than 256 bits is refused at construction, not at first request")
  void shortSecret_failsFast() {
    // Base64 of "too-short" - 9 bytes. Keys.hmacShaKeyFor rejects anything under 32.
    // It matters that this happens in the constructor: a deployment with a weak key must die on
    // boot, where someone is watching, rather than on the first login attempt at 3am.
    assertThatThrownBy(() -> new JwtService("dG9vLXNob3J0", EXPIRY_MS))
        .isInstanceOf(WeakKeyException.class);
  }

  @Test
  @DisplayName("src/main/resources/application.yml supplies NO default for JWT_SECRET")
  void productionConfig_hasNoFallbackSecret() throws Exception {
    // The one assertion that cannot be made from inside a Spring context: src/test/resources
    // shadows the production application.yml on the test classpath, so no test ever reads the
    // real file. Read it off disk instead.
    //
    // A default here would be worse than the bug this slice fixes. The old key is already in git
    // history; a committed fallback would mean every deployment that forgets to set JWT_SECRET
    // silently signs tokens anyone can forge, and nothing would ever surface it.
    String yaml = Files.readString(Path.of("src/main/resources/application.yml"));

    assertThat(yaml).contains("${JWT_SECRET}");
    // "${JWT_SECRET:anything}" is Spring's default syntax. It must not appear.
    assertThat(yaml).doesNotContain("${JWT_SECRET:");
  }

  // -------------------------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------------------------

  private static Key appKey() {
    return Keys.hmacShaKeyFor(Decoders.BASE64.decode(SECRET));
  }

  private static String signedWith(Key key, Instant issuedAt, Instant expiresAt) {
    return Jwts.builder()
        .setSubject("aziz@example.com")
        .setIssuedAt(Date.from(issuedAt))
        .setExpiration(Date.from(expiresAt))
        .signWith(key, SignatureAlgorithm.HS256)
        .compact();
  }
}
