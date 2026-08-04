package com.graduation.project.engine.core;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Arrays;
import java.util.Base64;
import javax.crypto.BadPaddingException;
import javax.crypto.IllegalBlockSizeException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Tests for {@link PasswordService}.
 *
 * <p>{@code encrypt}/{@code decrypt} are what turns a user's e-mail address into the
 * {@code ?token=...} of a password-reset link ({@code UserService.forgotPassword} ->
 * {@code MailService.sendForgotPasswordEmail}), and {@code changePassword} decrypts that same
 * token back.
 *
 * <h2>The canary, and why it no longer pins a literal</h2>
 *
 * <p>This class used to hold {@code "MZQJDqc5XqIXLMzs1s0xH5vuYocPc2b4HixySp4mBJQ="}, the exact
 * ciphertext of {@code user@example.com} under the old hard-coded key,
 * described as "the compatibility contract for every reset link that has already been e-mailed".
 *
 * <p>That contract is void. The key was a {@code private static final} literal in the source and
 * is present in three blobs of this repository's git history, so it is public knowledge - and
 * because {@code decrypt(token)} yields the e-mail address whose password is then changed,
 * <b>anyone holding it can mint a valid reset link for any address</b>, with no expiry. Every link
 * ever issued under that key is already forgeable. Preserving compatibility with those links would
 * be preserving the vulnerability, so the key is externalised and MUST be rotated, which changes
 * every ciphertext by design.
 *
 * <p>What the canary was for - catching a silent change of crypto - is kept, stated in terms that
 * do not depend on any particular key: a round trip through a SUPPLIED key returns the input
 * ({@link #encryptDecrypt_roundTripsUnderASuppliedKey()}), and a token minted under one key does
 * not decrypt under another ({@link #tokenFromOneKey_doesNotDecryptUnderAnother()}). A change to
 * mode, padding or key derivation still breaks these; a key rotation no longer does.
 */
class PasswordServiceTest {

  /**
   * Test-only keys, base64 of 16 ASCII bytes each (AES-128). They exist only in this file and
   * protect nothing - which is now possible to say, because the key is a constructor argument
   * rather than a compile-time constant baked into the class.
   */
  private static final String TEST_KEY = "dGVzdC1hZXMta2V5LTE2Yg==";
  private static final String OTHER_KEY = "YS1kaWZmZXJlbnQta2V5IQ==";

  private final PasswordService passwordService = new PasswordService(TEST_KEY);

  @Test
  @DisplayName("encrypt/decrypt: a round trip through a supplied key returns the input")
  void encryptDecrypt_roundTripsUnderASuppliedKey() throws Exception {
    // Replaces encrypt_pinsLiteralCiphertext. The property that actually matters to the feature
    // is that what comes back out is what went in, whatever the key happens to be.
    String plaintext = "somebody+tagged@sub.domain.example";

    assertThat(passwordService.decrypt(passwordService.encrypt(plaintext))).isEqualTo(plaintext);
  }

  @Test
  @DisplayName("CANARY: a token minted under one key does not decrypt under another")
  void tokenFromOneKey_doesNotDecryptUnderAnother() throws Exception {
    // The half of the canary that a fake fix cannot pass. Accepting the key as a constructor
    // parameter and then ignoring it - still encrypting under a baked-in constant - would satisfy
    // every other test in this class and leave the exposure exactly where it was. It cannot
    // satisfy this one: the two instances must genuinely disagree.
    //
    // This is also precisely what key ROTATION does to outstanding reset links, asserted rather
    // than assumed: after a rotation every link already in someone's inbox stops working.
    String token = passwordService.encrypt("user@example.com");
    PasswordService rotated = new PasswordService(OTHER_KEY);

    assertThatThrownBy(() -> rotated.decrypt(token))
        .as("a token from a foreign key must not silently yield a usable e-mail address")
        .isInstanceOfAny(BadPaddingException.class, IllegalBlockSizeException.class);
  }

  @Test
  @DisplayName("encrypt: same key + same input yields the same output - no IV, no salt, no nonce")
  void encrypt_isDeterministic() throws Exception {
    assertThat(passwordService.encrypt("user@example.com"))
        .isEqualTo(passwordService.encrypt("user@example.com"));
    // A second, independent instance holding the SAME key agrees. It is per-instance state now,
    // not a static, so this says the key is used and nothing else leaks in.
    assertThat(new PasswordService(TEST_KEY).encrypt("user@example.com"))
        .isEqualTo(passwordService.encrypt("user@example.com"));
  }

  @Test
  @DisplayName("decrypt: reads a ciphertext produced by a different instance holding the same key")
  void decrypt_readsCiphertextFromAnotherInstanceWithTheSameKey() throws Exception {
    // The property forgotPassword -> changePassword actually relies on: the two calls happen in
    // different requests, and formerly relied on the key being a shared static.
    String token = new PasswordService(TEST_KEY).encrypt("user@example.com");

    assertThat(passwordService.decrypt(token)).isEqualTo("user@example.com");
  }

  @Test
  @DisplayName("encrypt: is ECB - equal plaintext blocks map to equal ciphertext blocks")
  void encrypt_isElectronicCodebook() throws Exception {
    // Both inputs are exactly 16 chars, so block 2 of each is pure PKCS#5 padding and the two
    // ciphertexts share it verbatim. That leak is the signature of ECB mode and is kept so a later
    // slice moving to GCM/CBC is forced to acknowledge the format change.
    //
    // Rewritten to compare the actual padding BLOCK rather than a literal base64 tail, so it
    // describes ECB itself instead of one key's output.
    byte[] a = Base64.getDecoder().decode(passwordService.encrypt("user@example.com"));
    byte[] b = Base64.getDecoder().decode(passwordService.encrypt("aziz@example.com"));

    assertThat(a).isNotEqualTo(b);
    assertThat(a).hasSize(32);
    assertThat(Arrays.copyOfRange(a, 16, 32))
        .as("the all-padding second block is identical under ECB - that is the leak")
        .isEqualTo(Arrays.copyOfRange(b, 16, 32));
  }

  // -------------------------------------------------------------------------------------------
  // The key is configuration, and an unusable one must stop startup
  // -------------------------------------------------------------------------------------------

  @Test
  @DisplayName("constructor: a missing or blank key is refused, so the context cannot start without one")
  void constructor_blankKey_isRefused() {
    // src/main/resources/application.yml reads ${PASSWORD_RESET_AES_KEY} with NO default, so this
    // is what a deployment that forgot the variable hits - at startup, not at the first reset.
    assertThatThrownBy(() -> new PasswordService(null)).isInstanceOf(IllegalStateException.class);
    assertThatThrownBy(() -> new PasswordService("  ")).isInstanceOf(IllegalStateException.class);
  }

  @Test
  @DisplayName("constructor: a key that is not base64, or is the wrong length for AES, is refused")
  void constructor_unusableKey_isRefused() {
    assertThatThrownBy(() -> new PasswordService("not base64 at all !!"))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("Base64");

    // 15 bytes: AES takes 16, 24 or 32 and would otherwise fail later, per reset request, with
    // "Invalid AES key length" from the JCE.
    assertThatThrownBy(() -> new PasswordService(
        Base64.getEncoder().encodeToString(new byte[15])))
        .isInstanceOf(IllegalStateException.class)
        .hasMessageContaining("16, 24 or 32");

    // 32 bytes is fine - AES-256, and the length the dev key in src/test/resources uses.
    assertThat(new PasswordService(Base64.getEncoder().encodeToString(new byte[32])))
        .isNotNull();
  }

  @Test
  @DisplayName("decrypt: non-base64 garbage throws IllegalArgumentException (from the Base64 decoder)")
  void decrypt_nonBase64_throwsIllegalArgumentException() {
    assertThatThrownBy(() -> passwordService.decrypt("###not base64###"))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("Illegal base64 character");
  }

  @Test
  @DisplayName("decrypt: valid base64 that is not block-aligned throws IllegalBlockSizeException")
  void decrypt_notBlockAligned_throwsIllegalBlockSizeException() {
    String threeBytes = Base64.getEncoder().encodeToString(new byte[] {1, 2, 3});

    assertThatThrownBy(() -> passwordService.decrypt(threeBytes))
        .isInstanceOf(IllegalBlockSizeException.class)
        .hasMessageContaining("Input length must be multiple of 16");
  }

  @Test
  @DisplayName("decrypt: block-aligned but wrongly padded throws BadPaddingException")
  void decrypt_badPadding_throwsBadPaddingException() {
    String sixteenZeroBytes = Base64.getEncoder().encodeToString(new byte[16]);

    assertThatThrownBy(() -> passwordService.decrypt(sixteenZeroBytes))
        .isInstanceOf(BadPaddingException.class);
  }

  @Test
  @DisplayName("decrypt: the empty string is REFUSED, not quietly decrypted to the empty string")
  void decrypt_emptyString_isRefused() {
    // INVERTED. This previously read
    //
    //     assertThat(passwordService.decrypt("")).isEmpty();
    //
    // with the note that UserService.changePassword therefore did not fail here but fell through
    // to userRepository.findByEmail(""). That is the defect: AES/ECB over zero bytes is zero
    // bytes, no padding is checked because there is no block to check, and "" decrypts to "" -
    // so a reset request carrying no token at all looked to this method exactly like a valid one,
    // and the refusal happened three calls later for the wrong reason (no user has the e-mail "").
    //
    // IllegalArgumentException, matching what the Base64 decoder already raises for other
    // unusable inputs: an empty ciphertext is a bad argument, not a cryptographic outcome.
    assertThatThrownBy(() -> passwordService.decrypt(""))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("must not be null or blank");
  }

  @Test
  @DisplayName("decrypt: null and whitespace-only input are refused the same way")
  void decrypt_nullOrBlank_isRefused() {
    // null previously reached Base64.getDecoder().decode(null) and came back as a bare
    // NullPointerException; whitespace reached it and came back as "Illegal base64 character 20",
    // which describes the symptom rather than the cause. Both now say what is actually wrong.
    assertThatThrownBy(() -> passwordService.decrypt(null))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("must not be null or blank");

    assertThatThrownBy(() -> passwordService.decrypt("   "))
        .isInstanceOf(IllegalArgumentException.class)
        .hasMessageContaining("must not be null or blank");
  }

  @Test
  @DisplayName("hashPassword: BCrypt $2a$ cost 10, 60 chars, salted (two hashes differ)")
  void hashPassword_isSaltedBcrypt() {
    String first = passwordService.hashPassword("s3cret");
    String second = passwordService.hashPassword("s3cret");

    assertThat(first).startsWith("$2a$10$").hasSize(60);
    assertThat(first).isNotEqualTo(second);
  }

  @Test
  @DisplayName("verifyPassword: accepts the matching password, rejects anything else")
  void verifyPassword_matchesOnlyTheRightPassword() {
    String hash = passwordService.hashPassword("s3cret");

    assertThat(passwordService.verifyPassword("s3cret", hash)).isTrue();
    assertThat(passwordService.verifyPassword("wrong", hash)).isFalse();
  }
}
