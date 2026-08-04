package com.graduation.project.engine.core.securityConfig;

import com.graduation.project.engine.core.exception.CustomAuthenticationEntryPoint;
import com.graduation.project.engine.user.model.Role;
import java.time.Duration;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.logout.LogoutHandler;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
public class SecurityConfiguration {

  private final JwtAuthenticationFilter jwtAuthenticationFilter;
  private final AuthenticationProvider authenticationProvider;
  private final LogoutHandler logoutHandler;
  private static final String[] PUBLIC_URLS = {
      "/auth/forgot-password",
      "/auth/change-password",
      "/auth/register",
      "/event/get_image/**",

      "/auth/login",
      "/docs/**",
  };
  private static final String[] ADMIN_URLS = {
      "/event/countable-events/**",
      "/event/delete-events/**",
      "/auth/update-user/**",
      "/event/all-events",
      "/event/periodic-events/**",
      "/event/sendPdfEmail/**",
      "/event/pie-chart-events/**",
  };


  @Bean
  public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .csrf()
        .disable().cors(Customizer.withDefaults())
        .authorizeHttpRequests()
        .requestMatchers(PUBLIC_URLS).permitAll()
        .requestMatchers(ADMIN_URLS).hasAnyAuthority(Role.ADMIN.name())
        .anyRequest()
        .authenticated()
        .and()
        .exceptionHandling().authenticationEntryPoint(authenticationEntryPoint())
        .and()
        .sessionManagement()
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
        .and()
        .authenticationProvider(authenticationProvider)
        .addFilterBefore(jwtAuthenticationFilter, UsernamePasswordAuthenticationFilter.class)
        .logout().logoutUrl("/auth/logout").addLogoutHandler(logoutHandler)
        .logoutSuccessHandler(
            (request, response, authentication) -> SecurityContextHolder.clearContext());
    return http.build();
  }

  @Bean
  public AuthenticationEntryPoint authenticationEntryPoint() {
    return new CustomAuthenticationEntryPoint();
  }

  /**
   * The single CORS policy for the whole API.
   *
   * <h2>What this replaces</h2>
   *
   * <p>A bare {@code @CrossOrigin} on {@code EventController} and {@code UserController}. With no
   * attributes that annotation means {@code allowedOrigins = "*"}: <b>any</b> site could make
   * cross-origin calls to this API from a visitor's browser and read the responses - the auth
   * endpoints included, and {@code /event/get_image/**} included, which needs no token at all and
   * serves the worksite camera frame.
   *
   * <p>{@link #securityFilterChain} already called {@code .cors(Customizer.withDefaults())}. That
   * is not a policy - it means "use the {@code CorsConfigurationSource} bean". With no such bean,
   * Spring Security falls back to the {@code HandlerMappingIntrospector}, which is how the bare
   * annotations were reaching the filter chain in the first place. Declaring the bean is what moves
   * the decision here; the annotations were deleted so there is no second policy left to drift.
   *
   * <h2>Why the origins are configuration and not a constant</h2>
   *
   * <p>The set of trusted origins is the one thing about this policy that legitimately differs
   * between a laptop and production, so it is the one thing that is a property. Everything else -
   * the methods, the credential flag - is the same everywhere and is fixed here where it can be
   * reviewed in one place.
   */
  @Bean
  public CorsConfigurationSource corsConfigurationSource(
      @Value("${app.cors.allowed-origins}") List<String> allowedOrigins) {

    List<String> origins = allowedOrigins.stream()
        .map(String::trim)
        .filter(origin -> !origin.isEmpty())
        .toList();

    if (origins.isEmpty()) {
      throw new IllegalStateException(
          "app.cors.allowed-origins is empty. List the exact origin(s) the frontend is served "
              + "from, e.g. https://safety.example.com.");
    }
    // Refused rather than accepted, because "*" is precisely the setting this bean exists to
    // remove. Without this guard the defect is one config edit away from returning, and it would
    // return silently - a wildcard looks like a working configuration from every direction except
    // an attacker's.
    if (origins.contains("*")) {
      throw new IllegalStateException(
          "app.cors.allowed-origins must not be '*'. A wildcard lets any site call this API from "
              + "a browser; list the exact origins instead.");
    }

    CorsConfiguration configuration = new CorsConfiguration();
    // setAllowedOrigins, not setAllowedOriginPatterns: exact string matches only. Patterns would
    // reintroduce the question of whether "http://localhost:3000.evil.example.com" matches.
    configuration.setAllowedOrigins(origins);
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    // The frontend attaches `Authorization: Bearer ...` by hand on every authenticated call, which
    // makes those requests preflighted; refusing the header here would break every logged-in page.
    configuration.setAllowedHeaders(List.of("*"));
    // FALSE, and it must stay false. This API authenticates with a bearer token held in
    // localStorage and set by JavaScript - it uses no cookies and no HTTP auth - so it never needs
    // the browser to attach ambient credentials. Turning this on would only widen what a permitted
    // origin can do, and it is what makes an origin list a security boundary rather than a
    // formality.
    configuration.setAllowCredentials(false);
    configuration.setMaxAge(Duration.ofMinutes(30));

    UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", configuration);
    return source;
  }
}