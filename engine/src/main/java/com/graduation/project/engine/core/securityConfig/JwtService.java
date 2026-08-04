package com.graduation.project.engine.core.securityConfig;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.io.Decoders;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.stereotype.Service;

import java.security.Key;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;
import java.util.function.Function;

/**
 * Issues and verifies the HS256 bearer tokens the whole API is authenticated with.
 *
 * <h2>Why the secret is a constructor argument</h2>
 *
 * <p>It used to be {@code private static final String SECRET_KEY = "${JWT_SECRET}"} - the literal
 * six characters {@code ${...}}, left behind by a history rewrite rather than bound by Spring. A
 * {@code static final String} initialised with a constant expression is a compile-time constant
 * (JLS 4.12.4): javac inlines its value at every use site, so the field does not exist to be
 * written at runtime. {@code @Value} could not bind it and reflection could not rebind it. Making
 * the secret a constructor parameter is what removes the constant-ness; nothing less does.
 *
 * <p>The key is built once, in the constructor, so a deployment configured with a secret that is
 * blank, not Base64, or shorter than the 256 bits HS256 requires dies at context startup - loudly,
 * while somebody is watching - instead of at the first login attempt.
 *
 * <p><b>The secret has no default anywhere.</b> {@code src/main/resources/application.yml} reads
 * {@code ${JWT_SECRET}} with no fallback, so a missing environment variable is a startup failure.
 * A committed fallback would mean an unconfigured deployment silently signs tokens with a key that
 * is public knowledge, which is strictly worse than not starting.
 *
 * <h2>What this class throws</h2>
 *
 * <p>Every verification failure - expiry, a foreign signature, a malformed token - surfaces as an
 * unchecked {@link io.jsonwebtoken.JwtException}, and an empty or null token as a plain
 * {@link IllegalArgumentException}. None of them are checked, so nothing forces a caller to handle
 * them; {@link JwtAuthenticationFilter} does, because it runs outside {@code DispatcherServlet}
 * where an escaping exception is an uncatchable 500 rather than a 403.
 */
@Service
public class JwtService {

  private final Key signInKey;
  private final long expirationMillis;

  public JwtService(
      @Value("${jwt.secret}") String secret,
      @Value("${jwt.expiration-ms}") long expirationMillis) {

    if (secret == null || secret.isBlank()) {
      throw new IllegalStateException(
          "JWT_SECRET is empty. Set it to a Base64-encoded key of at least 256 bits; "
              + "there is deliberately no default.");
    }
    // Both of these throw: DecodingException if the value is not Base64, WeakKeyException if the
    // decoded key is under 256 bits. Deliberately not caught - either one must stop startup.
    this.signInKey = Keys.hmacShaKeyFor(Decoders.BASE64.decode(secret));
    this.expirationMillis = expirationMillis;
  }

  public String extractUsername(String token) {
    return extractClaim(token, Claims::getSubject);
  }

  public <T> T extractClaim(String token, Function<Claims, T> claimsResolver) {
    final Claims claims = extractAllClaims(token);
    return claimsResolver.apply(claims);
  }

  public String generateToken(UserDetails userDetails) {
    return generateToken(new HashMap<>(), userDetails);
  }

  public String generateToken(Map<String, Object> extraClaims, UserDetails userDetails) {
    // ONE clock read for both claims. Reading System.currentTimeMillis() separately for iat and
    // exp let the millisecond tick between them, and since JWT timestamps are whole seconds that
    // made the token's lifetime 1201 seconds instead of 1200 about once in a thousand tokens.
    long now = System.currentTimeMillis();
    return Jwts.builder()
        .setClaims(extraClaims)
        .claim("authorities", userDetails.getAuthorities())
        .setSubject(userDetails.getUsername())
        .setIssuedAt(new Date(now))
        .setExpiration(new Date(now + expirationMillis))
        .signWith(signInKey, SignatureAlgorithm.HS256)
        .compact();
  }

  public boolean isTokenValid(String token, UserDetails userDetails) {
    final String username = extractUsername(token);
    return username.equals(userDetails.getUsername()) && !isTokenExpired(token);
  }

  private boolean isTokenExpired(String token) {
    return extractExpiration(token).before(new Date());
  }

  private Date extractExpiration(String token) {
    return extractClaim(token, Claims::getExpiration);
  }

  private Claims extractAllClaims(String token) {
    return Jwts.parserBuilder()
        .setSigningKey(signInKey)
        .build().parseClaimsJws(token).getBody();
  }
}
