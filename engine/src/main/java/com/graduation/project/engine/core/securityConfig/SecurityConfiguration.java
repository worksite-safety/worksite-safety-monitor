package com.graduation.project.engine.core.securityConfig;

import com.graduation.project.engine.core.exception.CustomAuthenticationEntryPoint;
import com.graduation.project.engine.user.model.Role;
import lombok.RequiredArgsConstructor;
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
      "/auth/login",
      "/event/countable-events/**",
      "/auth/register",
      "/docs/**",
      "/mail/**",


  };
  private static final String[] ADMIN_URLS = {
      "/auth/role/**",
      "/auth/{id}",
  };
  private static final String[] USER_URLS = {
      "/demo/authreq"

  };

  @Bean
  public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .csrf()
        .disable().cors(Customizer.withDefaults())
        .authorizeHttpRequests()
        .requestMatchers(PUBLIC_URLS).permitAll()
        .requestMatchers(USER_URLS)
        .hasAnyAuthority(Role.ADMIN.name(), Role.USER.name(), Role.MANAGER.name())
        .requestMatchers(ADMIN_URLS).hasAnyAuthority(Role.ADMIN.name(), Role.MANAGER.name())
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

}