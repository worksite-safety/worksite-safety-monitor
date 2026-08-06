package com.graduation.project.engine.core.apiDocumentation;

/**
 * Values for the OpenAPI document {@link SpringdocConfig} serves at {@code /docs}.
 *
 * <p>That document is the only machine-readable description this system publishes, which made it
 * the only place a consumer could be told the licence - and it declared {@code
 * "Apache License 2.1.0"}, a version that has never existed, against the Apache-2.0 URL, for a
 * project that is AGPL-3.0-or-later. A reader had no way to tell whether the name or the URL was
 * the mistake, and either reading was permissive where the project is copyleft.
 *
 * <p>The contact named "CodeRunners": a company that does not exist, an email at a domain with no
 * MX records, and one maintainer's personal LinkedIn profile. It is now the repository's issue
 * tracker, because that address moves with the project rather than with whoever is maintaining it
 * or with which accounts they still hold. No email is published: {@code SECURITY.md} routes a
 * private report to the address on a maintainer's recent commits, so there is none to invent here.
 */
public class SwaggerConstant {

  public static final String CONTACT_NAME = "Worksite Safety Monitor maintainers";
  public static final String CONTACT_URL =
      "https://github.com/worksite-safety/worksite-safety-monitor/issues";
  public static final String API_TITLE = "Worksite Safety Monitor API";
  public static final String API_VERSION = "1.0";
  public static final String LICENSE = "AGPL-3.0-or-later";
  public static final String LICENSE_URL = "https://www.gnu.org/licenses/agpl-3.0.html";
}
