package com.graduation.project.engine.core;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.Yaml;

/**
 * The externalisation policy, asserted against the REAL production configuration file.
 *
 * <h2>Why this reads a file instead of a Spring context</h2>
 *
 * <p>{@code src/test/resources/application.yml} shadows {@code src/main/resources/application.yml}
 * on the test classpath - deliberately, so no test can reach real credentials. The consequence is
 * that <b>nothing else in this suite ever looks at the production file at all</b>. Every guarantee
 * that file is supposed to carry ("the JWT secret has no fallback", "the image path is not somebody
 * else's laptop") is therefore unenforced by the build, and the way each of these defects arrived
 * in the first place was somebody editing that file with nothing watching.
 *
 * <p>So this class reads the file from the source tree as text and asserts on the RAW placeholder
 * strings, before any resolution. That is the only vantage point from which "has no default" is
 * even expressible: once Spring has resolved a placeholder, a value that came from a committed
 * fallback and a value that came from the environment are indistinguishable.
 *
 * <h2>The two rules</h2>
 *
 * <ul>
 *   <li><b>Secrets have NO default.</b> {@code ${VAR}} with no {@code :fallback}, so a deployment
 *       that forgets the variable fails to start rather than running on a key that is public
 *       knowledge.</li>
 *   <li><b>Everything else HAS a default, and the default works on any machine.</b> A required
 *       variable that is not a secret buys nothing and costs a failed boot; an absolute path to a
 *       former developer's home directory is worse than either.</li>
 * </ul>
 */
class ProductionConfigurationTest {

  /**
   * Resolved from {@code user.dir}, which Surefire sets to the module base directory. The file is
   * NOT loaded from the classpath on purpose: {@code classpath:/application.yml} resolves to
   * {@code target/test-classes}, i.e. the shadowing test file, which is precisely the file this
   * class is not interested in.
   */
  private static final Path PRODUCTION_YAML =
      Path.of("src", "main", "resources", "application.yml");

  /** {@code ${NAME}} or {@code ${NAME:default}} - group 1 is the name, group 2 the default. */
  private static final Pattern PLACEHOLDER =
      Pattern.compile("\\$\\{([A-Za-z0-9_.\\-]+)(?::([^}]*))?}");

  private static String rawText;
  private static Map<String, Object> tree;

  @BeforeAll
  @SuppressWarnings("unchecked")
  static void loadTheProductionFile() throws IOException {
    assertThat(PRODUCTION_YAML)
        .as("the production configuration file must be where this test expects it")
        .exists();
    rawText = Files.readString(PRODUCTION_YAML, StandardCharsets.UTF_8);
    try (InputStream in = Files.newInputStream(PRODUCTION_YAML)) {
      tree = (Map<String, Object>) new Yaml().load(in);
    }
  }

  // -------------------------------------------------------------------------------------------
  // Secrets: no default, anywhere
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("every secret is an environment variable with NO committed fallback")
  void secretsHaveNoDefault() {
    // The SMTP password is in this list because a Gmail app password was committed here. It was
    // removed from the file and from the history, and it STILL has to be revoked at the provider -
    // see MAIL_PASSWORD's comment in the file itself. Relocating a credential does not un-leak it.
    assertThat(value("spring.mail.password")).isEqualTo("${MAIL_PASSWORD}");
    assertThat(value("jwt.secret")).isEqualTo("${JWT_SECRET}");
    assertThat(value("password-reset.aes-key")).isEqualTo("${PASSWORD_RESET_AES_KEY}");
  }

  @Test
  @DisplayName("the set of variables that are REQUIRED at startup is exactly the set of secrets")
  void onlySecretsAreRequiredAtStartup() {
    // This is the test that answers "what happens if I forget one?" for every property at once.
    // A name in this set means: no fallback, so Spring cannot resolve the placeholder and the
    // context refuses to start. A name NOT in it means the application boots without it.
    //
    // It is pinned as an exact set rather than a contains-check so that BOTH mistakes are caught:
    // demoting a secret to a committed default (it silently disappears from here), and adding a
    // required variable for something that is not a secret (a new deployment fails to boot for a
    // value that could have had a sane default).
    //
    // MAIL_USERNAME is in the list with MAIL_PASSWORD because the two are one credential, and
    // because MailService also uses the username as the From address of every alert and reset
    // mail - a committed default would put a wrong, permanent sender identity on outbound mail
    // instead of failing. It was already required before this change; it is recorded here rather
    // than quietly relaxed.
    assertThat(placeholdersWithoutDefault())
        .containsExactlyInAnyOrder(
            "MAIL_USERNAME", "MAIL_PASSWORD", "JWT_SECRET", "PASSWORD_RESET_AES_KEY");
  }

  // -------------------------------------------------------------------------------------------
  // Non-secrets: a default that works on a machine that is not the author's
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("event.image.path defaults to a RELATIVE path, not a developer's home directory")
  void imagePathDefaultIsRelative() {
    String imagePath = value("event.image.path");

    String fallback = defaultOf(imagePath);
    assertThat(fallback)
        .as("event.image.path must carry a default so the app starts on a fresh checkout")
        .isNotNull();

    // The original value was an absolute path into a former developer's OneDrive folder, so the
    // video preview was broken on every machine except one, and the failure mode was a 404 from a
    // PUBLIC endpoint - nothing in a log, nothing on screen but a missing image.
    assertThat(fallback).doesNotContain(":");        // no C:/... drive letter
    assertThat(fallback).doesNotStartWith("/");      // no absolute POSIX path
    assertThat(fallback).doesNotContain("Users");
    assertThat(fallback).startsWith(".");
  }

  @Test
  @DisplayName("no configured VALUE is an absolute path into somebody's home directory")
  void noAbsoluteHomeDirectoryPathsRemain() {
    // Values only, never the comments. The first version of this test scanned the raw text and
    // failed on the comment that EXPLAINS the removed OneDrive path - which would have meant the
    // check could only stay green by deleting the documentation of the defect it guards against.
    // snakeyaml drops comments, so walking the parsed tree separates prose from configuration.
    for (String configured : allScalarValues()) {
      String normalised = configured.replace('\\', '/');
      assertThat(normalised)
          .as("configured value: %s", configured)
          .doesNotContainIgnoringCase("c:/users")
          .doesNotContainIgnoringCase("/home/")
          .doesNotContainIgnoringCase("onedrive");
    }
  }

  @Test
  @DisplayName("the password-reset link's host is configuration, not a constant in MailService")
  void frontendBaseUrlIsConfigured() {
    // MailService built the reset link from a hardcoded "http://localhost:3000/change-password".
    // Every reset mail a deployed instance sent pointed the recipient at their OWN machine, where
    // nothing was listening - the mail arrived, the link was dead, and the server had no idea.
    String baseUrl = value("app.frontend.base-url");

    assertThat(baseUrl).as("app.frontend.base-url must exist").isNotNull();
    assertThat(resolvedDefault(baseUrl)).isNotBlank();
  }

  @Test
  @DisplayName("CORS names the origins it trusts, and '*' is not one of them")
  void corsAllowedOriginsIsAnExplicitList() {
    // @CrossOrigin with no attributes on the controllers meant allowedOrigins = "*": any site on
    // the internet could call this API from a victim's browser and read the response.
    String origins = value("app.cors.allowed-origins");

    assertThat(origins).as("app.cors.allowed-origins must exist").isNotNull();
    assertThat(resolvedDefault(origins))
        .as("a wildcard here reinstates the defect this property exists to close")
        .isNotBlank()
        .isNotEqualTo("*")
        .doesNotContain("*");
  }

  // -------------------------------------------------------------------------------------------
  // helpers
  // -------------------------------------------------------------------------------------------

  /** The RAW value at a dotted key - placeholders unresolved, exactly as committed. */
  private static String value(String dottedKey) {
    Object current = tree;
    for (String segment : dottedKey.split("\\.")) {
      if (!(current instanceof Map<?, ?> map)) {
        return null;
      }
      current = map.get(segment);
    }
    return current == null ? null : current.toString();
  }

  /** The {@code default} in {@code ${NAME:default}}, or null when the placeholder has none. */
  private static String defaultOf(String rawValue) {
    Matcher matcher = PLACEHOLDER.matcher(rawValue);
    return matcher.find() ? matcher.group(2) : null;
  }

  /** What this property evaluates to when the environment variable is absent. */
  private static String resolvedDefault(String rawValue) {
    Matcher matcher = PLACEHOLDER.matcher(rawValue);
    if (!matcher.find()) {
      return rawValue;
    }
    return matcher.group(2) == null ? null : matcher.group(2);
  }

  /** Every scalar value in the file, as a string. Keys and comments excluded. */
  private static Set<String> allScalarValues() {
    Set<String> values = new LinkedHashSet<>();
    collectScalars(tree, values);
    return values;
  }

  private static void collectScalars(Object node, Set<String> sink) {
    if (node instanceof Map<?, ?> map) {
      map.values().forEach(child -> collectScalars(child, sink));
    } else if (node instanceof Iterable<?> items) {
      items.forEach(child -> collectScalars(child, sink));
    } else if (node != null) {
      sink.add(node.toString());
    }
  }

  /** Every {@code ${VAR}} in the file that has no {@code :fallback} - i.e. required at startup. */
  private static Set<String> placeholdersWithoutDefault() {
    Set<String> required = new LinkedHashSet<>();
    Matcher matcher = PLACEHOLDER.matcher(rawText);
    while (matcher.find()) {
      if (matcher.group(2) == null) {
        required.add(matcher.group(1));
      }
    }
    return required;
  }
}
