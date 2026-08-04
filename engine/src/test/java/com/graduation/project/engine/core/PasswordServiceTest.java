package com.graduation.project.engine.core;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Base64;
import javax.crypto.BadPaddingException;
import javax.crypto.IllegalBlockSizeException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * Characterization tests for {@link PasswordService}.
 *
 * <p>{@code encrypt}/{@code decrypt} are what turns a user's e-mail address into the
 * {@code ?token=...} of a password-reset link ({@code UserService.forgotPassword} ->
 * {@code MailService.sendForgotPasswordEmail}), and {@code changePassword} decrypts that same
 * token back. The transform is a keyless-per-call AES/ECB with a hard-coded key, so it is fully
 * deterministic: <b>the literal ciphertext below is the compatibility contract for every reset
 * link that has already been e-mailed.</b> If someone "improves" the crypto (a random IV, a
 * different mode, a different key) without a compatibility path, every outstanding link silently
 * stops working - and this literal is the canary that says so.
 */
class PasswordServiceTest {

  private final PasswordService passwordService = new PasswordService();

  /** Base64(AES/ECB/PKCS5Padding("user@example.com", key "5A7134743777217A")). */
  private static final String USER_EXAMPLE_COM_CIPHERTEXT =
      "MZQJDqc5XqIXLMzs1s0xH5vuYocPc2b4HixySp4mBJQ=";

  @Test
  @DisplayName("encrypt: pins the exact ciphertext of a fixed input (reset-link compatibility)")
  void encrypt_pinsLiteralCiphertext() throws Exception {
    assertThat(passwordService.encrypt("user@example.com"))
        .isEqualTo(USER_EXAMPLE_COM_CIPHERTEXT);
  }

  @Test
  @DisplayName("encrypt: same input always yields the same output - no IV, no salt, no nonce")
  void encrypt_isDeterministic() throws Exception {
    assertThat(passwordService.encrypt("user@example.com"))
        .isEqualTo(passwordService.encrypt("user@example.com"));
    // A second, independent instance agrees too: the key is a static field, not per-instance.
    assertThat(new PasswordService().encrypt("user@example.com"))
        .isEqualTo(USER_EXAMPLE_COM_CIPHERTEXT);
  }

  @Test
  @DisplayName("encrypt/decrypt round-trips")
  void encryptDecrypt_roundTrips() throws Exception {
    String plaintext = "somebody+tagged@sub.domain.example";

    assertThat(passwordService.decrypt(passwordService.encrypt(plaintext))).isEqualTo(plaintext);
  }

  @Test
  @DisplayName("decrypt: reads a ciphertext produced by a different instance (static key)")
  void decrypt_readsTheLiteralCiphertext() throws Exception {
    assertThat(passwordService.decrypt(USER_EXAMPLE_COM_CIPHERTEXT))
        .isEqualTo("user@example.com");
  }

  @Test
  @DisplayName("encrypt: is ECB - equal plaintext blocks map to equal ciphertext blocks")
  void encrypt_isElectronicCodebook() throws Exception {
    // Both inputs are exactly 16 chars, so block 2 of each is pure PKCS#5 padding and the two
    // ciphertexts share it verbatim. That leak is the signature of ECB mode and is pinned so a
    // later slice that moves to GCM/CBC is forced to acknowledge the format change.
    String a = passwordService.encrypt("user@example.com");
    String b = passwordService.encrypt("aziz@example.com");

    assertThat(a).isNotEqualTo(b);
    String sharedPaddingBlock = "5vuYocPc2b4HixySp4mBJQ=";
    assertThat(a).endsWith(sharedPaddingBlock);
    assertThat(b).endsWith(sharedPaddingBlock);
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
  @DisplayName("decrypt: SURPRISE - the empty string decrypts to the empty string without throwing")
  void decrypt_emptyString_returnsEmptyString() throws Exception {
    // Consequence: UserService.changePassword with secretKey "" does not fail here; it falls
    // through to userRepository.findByEmail(""), which is where it actually errors.
    assertThat(passwordService.decrypt("")).isEmpty();
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
