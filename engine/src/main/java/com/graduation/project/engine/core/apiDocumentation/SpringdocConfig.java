package com.graduation.project.engine.core.apiDocumentation;

import static com.graduation.project.engine.core.apiDocumentation.SwaggerConstant.API_TITLE;
import static com.graduation.project.engine.core.apiDocumentation.SwaggerConstant.API_VERSION;
import static com.graduation.project.engine.core.apiDocumentation.SwaggerConstant.CONTACT_NAME;
import static com.graduation.project.engine.core.apiDocumentation.SwaggerConstant.CONTACT_URL;
import static com.graduation.project.engine.core.apiDocumentation.SwaggerConstant.LICENSE;
import static com.graduation.project.engine.core.apiDocumentation.SwaggerConstant.LICENSE_URL;

import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    bearerFormat = "JWT",
    scheme = "bearer"
)
public class SpringdocConfig {

  @Bean
  public OpenAPI baseOpenAPI() {
    Components components = new Components();

    Info myInfo = new Info();
    myInfo.title(API_TITLE)
        .version(API_VERSION)
        // No .email(): every field of the OpenAPI contact object is optional, so leaving it unset
        // omits the key rather than publishing an empty one.
        .contact(new Contact().name(CONTACT_NAME).url(CONTACT_URL))
        .license(new License().url(LICENSE_URL).name(LICENSE));

    return new OpenAPI().components(components).
        info(myInfo);
  }
}