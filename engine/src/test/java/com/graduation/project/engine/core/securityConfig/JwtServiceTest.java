package com.graduation.project.engine.core.securityConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.graduation.project.engine.user.model.Role;
import com.graduation.project.engine.user.model.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.io.DecodingException;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.security.core.userdetails.UserDetails;

/**
 * Characterization tests for {@link JwtService}.
 *
 * <p><b>DEFECT PINNED HERE, NOT FIXED.</b> {@code JwtService.SECRET_KEY} is the literal string
 * {@code "${JWT_SECRET}"} - a placeholder left behind by a history rewrite, not a {@code @Value}
 * binding (the field is a {@code private static final String}, so it is a compile-time constant
 * and is inlined at its use site; no amount of reflection can rebind it).
 * {@code Decoders.BASE64.decode("${JWT_SECRET}")} therefore throws, and it throws in
 * {@code getSignInKey()}, which is the FIRST thing every public method reaches.
 *
 * <p>Consequences, all pinned below: no token can be issued, no token can be read, and
 * {@link JwtAuthenticationFilter} explodes on any request that carries an
 * {@code Authorization: Bearer} header (see {@code SecurityMatrixTest}).
 *
 * <p>Because generation is unreachable, the token's own {@code authorities} claim shape and its
 * 20-minute expiry cannot be asserted through {@code JwtService}'s public API at all. The last
 * test below pins the {@code authorities} rendering through the same jjwt + Jackson stack as a
 * deliberate PROXY canary, so a jjwt or Spring Security upgrade that changes how
 * {@code SimpleGrantedAuthority} serialises still trips a test. The 20-minute expiry
 * ({@code 1000 * 60 * 20} in {@code generateToken}) is a literal in production code and has no
 * reachable assertion; it is called out in the slice report instead.
 */
class JwtServiceTest {

  private final JwtService jwtService = new JwtService();

  private static final UserDetails ADMIN = User.builder()
      .email("aziz@example.com")
      .password("irrelevant")
      .role(Role.ADMIN)
      .build();

  /** A syntactically well-formed-looking JWT. It is never actually parsed - the key fails first. */
  private static final String ANY_TOKEN =
      "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhQGIuY29tIn0.c2lnbmF0dXJl";

  @Test
  @DisplayName("generateToken(userDetails) throws DecodingException - the secret is not base64")
  void generateToken_throwsDecodingException() {
    assertThatThrownBy(() -> jwtService.generateToken(ADMIN))
        .isInstanceOf(DecodingException.class)
        .hasMessage("Illegal base64 character: '_'");
  }

  @Test
  @DisplayName("generateToken(extraClaims, userDetails) throws DecodingException too")
  void generateTokenWithExtraClaims_throwsDecodingException() {
    assertThatThrownBy(() -> jwtService.generateToken(Map.of("k", "v"), ADMIN))
        .isInstanceOf(DecodingException.class);
  }

  @Test
  @DisplayName("extractUsername throws DecodingException for any token")
  void extractUsername_throwsDecodingException() {
    assertThatThrownBy(() -> jwtService.extractUsername(ANY_TOKEN))
        .isInstanceOf(DecodingException.class)
        .hasMessage("Illegal base64 character: '_'");
  }

  @Test
  @DisplayName("extractUsername(null) throws DecodingException, NOT a NullPointerException")
  void extractUsername_nullToken_stillFailsOnTheKeyFirst() {
    // The key is built before the token is looked at, so the token argument never matters.
    // This is why JwtAuthenticationFilter cannot even reject a malformed Bearer header cleanly.
    assertThatThrownBy(() -> jwtService.extractUsername(null))
        .isInstanceOf(DecodingException.class);
  }

  @Test
  @DisplayName("extractClaim throws DecodingException before the resolver is ever applied")
  void extractClaim_throwsDecodingException() {
    assertThatThrownBy(() -> jwtService.extractClaim(ANY_TOKEN, Claims::getSubject))
        .isInstanceOf(DecodingException.class);
  }

  @Test
  @DisplayName("isTokenValid throws DecodingException rather than returning false")
  void isTokenValid_throwsDecodingException() {
    // Note it THROWS - callers that expect a boolean (JwtAuthenticationFilter) get an
    // unchecked exception propagated out of the servlet filter chain instead.
    assertThatThrownBy(() -> jwtService.isTokenValid(ANY_TOKEN, ADMIN))
        .isInstanceOf(DecodingException.class);
  }

  @Test
  @DisplayName("DecodingException is unchecked (a JwtException), so nothing is forced to catch it")
  void decodingExceptionIsUnchecked() {
    Throwable thrown = org.assertj.core.api.Assertions.catchThrowable(
        () -> jwtService.generateToken(ADMIN));

    assertThat(thrown).isInstanceOf(RuntimeException.class);
    assertThat(thrown).isInstanceOf(io.jsonwebtoken.JwtException.class);
  }

  @Test
  @DisplayName("PROXY canary: SimpleGrantedAuthority serialises as {\"authority\":\"ADMIN\"} objects")
  void authoritiesClaimRendersAsObjects() {
    // JwtService cannot produce a token (see the class javadoc), so this rebuilds the exact
    // builder chain from JwtService.generateToken against a valid key. It pins the jjwt +
    // Jackson rendering of Spring Security's SimpleGrantedAuthority, which is the part an
    // upgrade is most likely to change silently: a switch to a plain string array here would
    // break every already-issued token and every consumer of the claim.
    Key key = Keys.hmacShaKeyFor(Base64.getDecoder()
        .decode("dGVzdC1zZWNyZXQta2V5LWZvci1qd3QtY2hhcmFjdGVyaXphdGlvbi0xMjM0NQ=="));

    String token = Jwts.builder()
        .claim("authorities", ADMIN.getAuthorities())
        .setSubject(ADMIN.getUsername())
        .setIssuedAt(new Date(System.currentTimeMillis()))
        .setExpiration(new Date(System.currentTimeMillis() + 1000 * 60 * 20))
        .signWith(key, SignatureAlgorithm.HS256)
        .compact();

    String payload = new String(Base64.getUrlDecoder().decode(token.split("\\.")[1]),
        StandardCharsets.UTF_8);
    assertThat(payload).contains("\"authorities\":[{\"authority\":\"ADMIN\"}]");
    assertThat(payload).contains("\"sub\":\"aziz@example.com\"");

    Claims claims = Jwts.parserBuilder().setSigningKey(key).build()
        .parseClaimsJws(token).getBody();
    assertThat(claims.get("authorities")).isInstanceOf(List.class);
    assertThat((List<?>) claims.get("authorities"))
        .singleElement()
        .isEqualTo(Map.of("authority", "ADMIN"));
  }
}
