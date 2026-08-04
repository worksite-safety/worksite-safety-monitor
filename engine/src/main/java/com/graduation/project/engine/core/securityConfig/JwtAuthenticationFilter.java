package com.graduation.project.engine.core.securityConfig;

import com.graduation.project.engine.user.repository.TokenRepository;
import io.jsonwebtoken.JwtException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.lang.NonNull;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.authentication.WebAuthenticationDetailsSource;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

  private final JwtService jwtService;
  private final UserDetailsService userDetailsService;
  private final TokenRepository tokenRepository;

  @Override
  protected void doFilterInternal(
      @NonNull HttpServletRequest request,
      @NonNull HttpServletResponse response,
      @NonNull FilterChain filterChain
  ) throws ServletException, IOException {

    final String authHeader = request.getHeader("Authorization");

    if (authHeader != null && authHeader.startsWith("Bearer ")) {
      authenticateIfTokenIsGood(request, authHeader.substring(7));
    }

    // Exactly one call, on every path. A token we cannot verify leaves the SecurityContext empty
    // and the request carries on as anonymous, which is what lets the AuthorizationFilter deny it
    // through CustomAuthenticationEntryPoint like any other unauthenticated request.
    filterChain.doFilter(request, response);
  }

  private void authenticateIfTokenIsGood(HttpServletRequest request, String jwt) {
    try {
      String userEmail = jwtService.extractUsername(jwt);

      if (userEmail == null || SecurityContextHolder.getContext().getAuthentication() != null) {
        return;
      }

      UserDetails userDetails = this.userDetailsService.loadUserByUsername(userEmail);

      var isTokenValid = tokenRepository.findByToken(jwt)
          .map(t -> !t.isExpired() && !t.isRevoked())
          .orElse(false);

      if (jwtService.isTokenValid(jwt, userDetails) && isTokenValid) {
        UsernamePasswordAuthenticationToken authenticationToken =
            new UsernamePasswordAuthenticationToken(
                userDetails,
                null,
                userDetails.getAuthorities()
            );
        authenticationToken.setDetails(new WebAuthenticationDetailsSource().buildDetails(request));

        SecurityContextHolder.getContext().setAuthentication(authenticationToken);
      }
    } catch (JwtException | IllegalArgumentException e) {
      // A token that will not verify is an ordinary authentication outcome, not a server fault,
      // and this filter is the last place that can say so: it runs BEFORE DispatcherServlet, so
      // anything thrown here escapes the servlet filter chain where no @ControllerAdvice can
      // reach it. The client would get a bare 500 - on public endpoints too, since this filter
      // inspects the header before any authorization decision is made. One stale token in a
      // browser was enough to make the whole API answer 500.
      //
      // IllegalArgumentException is caught alongside JwtException on purpose. jjwt raises
      // JwtException for expiry, foreign signatures and malformed tokens, but a plain
      // IllegalArgumentException for a null or empty token - which is exactly what the header
      // "Authorization: Bearer " (nothing after the space) produces. Catching only JwtException
      // leaves that one case still returning 500.
      //
      // DEBUG, not WARN: an expired token is the single most common thing that reaches this line,
      // it is entirely routine, and logging it at WARN would let any anonymous caller flood the
      // logs by sending garbage. The message carries no token material.
      logger.debug("Rejecting unverifiable bearer token: " + e.getClass().getSimpleName(), e);
    }
  }
}
