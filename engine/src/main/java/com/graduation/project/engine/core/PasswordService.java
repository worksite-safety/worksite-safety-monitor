package com.graduation.project.engine.core;

import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;

/**
 * Password hashing, and the reversible transform behind password-reset links.
 *
 * <h2>Why the AES key is a constructor argument</h2>
 *
 * <p>It used to be {@code private static final String secretKey = "<a 16-character literal>"}. A
 * {@code static final String} initialised with a constant expression is a compile-time constant
 * (JLS 4.12.4): javac inlines its value at every use site, so the field does not exist at runtime
 * to be written. Neither {@code @Value} nor reflection can reach it. Making the key a constructor
 * parameter is what removes the constant-ness; nothing less does.
 *
 * <h2>This is an account-takeover key, and it must be ROTATED, not merely moved</h2>
 *
 * <p>{@code encrypt(email)} produces the token in a reset link and {@code decrypt(token)} yields
 * the address whose password is then changed. The token carries no expiry and no binding to a
 * request, so <b>anyone holding this key can mint a valid reset link for any address at any
 * time</b>.
 *
 * <p>The old literal is present in three blobs of this repository's git history, so it must be
 * treated as public. It is no longer in the working tree - commit 4363391 removed it from both
 * this class and its test - but relocating it to configuration would not have undone the
 * disclosure either; only issuing a new key does. Rotation invalidates every reset link that has
 * already been e-mailed, which is the correct outcome: those links are forgeable by anyone who
 * can read the history.
 *
 * <p><b>No default anywhere.</b> {@code src/main/resources/application.yml} reads
 * {@code ${PASSWORD_RESET_AES_KEY}} with no fallback, so a missing variable is a startup failure.
 * A committed fallback would mean an unconfigured deployment silently minting reset tokens under a
 * key that is public knowledge - strictly worse than not starting. The only value in this
 * repository lives in {@code src/test/resources/application.yml} and protects nothing.
 *
 * <h2>What this still is not</h2>
 *
 * <p>AES/ECB over an e-mail address is a poor reset token even under a secret key: deterministic,
 * unexpiring, not revocable, and it leaks block structure. The correct design is an opaque random
 * token stored server-side with an expiry, which is larger than this change; see the accompanying
 * report. What is closed here is the disclosure.
 */
@Component
public class PasswordService {

  private static final String AES = "AES";

  /** Per-instance, built once from configuration - deliberately not static, not a constant. */
  private final SecretKey secretKey;

  private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

  public PasswordService(@Value("${password-reset.aes-key}") String aesKey) {
    if (aesKey == null || aesKey.isBlank()) {
      throw new IllegalStateException(
          "PASSWORD_RESET_AES_KEY is empty. Set it to a Base64-encoded AES key of 16, 24 or 32 "
              + "bytes; there is deliberately no default.");
    }

    byte[] keyBytes;
    try {
      keyBytes = Base64.getDecoder().decode(aesKey);
    } catch (IllegalArgumentException e) {
      // Rethrown as IllegalStateException so a misconfigured key reads as a configuration fault at
      // startup, not as a bad argument from whoever happened to trigger construction.
      throw new IllegalStateException(
          "PASSWORD_RESET_AES_KEY is not valid Base64. Generate one with: openssl rand -base64 32",
          e);
    }

    // Checked here, once, instead of surfacing as "Invalid AES key length" from the JCE on every
    // reset request. Base64-encoded like JwtService's secret, so the key can be full-entropy
    // random bytes rather than 16 typeable characters.
    if (keyBytes.length != 16 && keyBytes.length != 24 && keyBytes.length != 32) {
      throw new IllegalStateException(
          "PASSWORD_RESET_AES_KEY must decode to 16, 24 or 32 bytes (AES-128/192/256), but decoded "
              + "to " + keyBytes.length + " bytes.");
    }

    this.secretKey = new SecretKeySpec(keyBytes, AES);
  }

  public String hashPassword(String password) {
    return passwordEncoder.encode(password);
  }

  public boolean verifyPassword(String rawPassword, String hashedPassword) {
    return passwordEncoder.matches(rawPassword, hashedPassword);
  }

  public String encrypt(String data) throws Exception {
    Cipher cipher = Cipher.getInstance(AES);
    cipher.init(Cipher.ENCRYPT_MODE, secretKey);
    byte[] encryptedData = cipher.doFinal(data.getBytes());
    return Base64.getEncoder().encodeToString(encryptedData);
  }

  public String decrypt(String encryptedData) throws Exception {
    // An empty ciphertext is not a decryptable value, but AES/ECB never said so: zero bytes in is
    // zero bytes out, and PKCS#5 padding is never inspected because there is no block to inspect.
    // decrypt("") therefore returned "" and a password-reset request carrying no token at all was
    // indistinguishable here from a genuine one - the failure surfaced later and elsewhere, as
    // "User Not Found: " from findByEmail(""), which names the wrong problem.
    //
    // Blank as well as empty: whitespace reached the Base64 decoder and came back as
    // "Illegal base64 character 20", a message about a symptom. Neither case is recoverable, so
    // both are refused here, at the boundary, before any key is touched.
    if (encryptedData == null || encryptedData.isBlank()) {
      throw new IllegalArgumentException("encryptedData must not be null or blank");
    }

    Cipher cipher = Cipher.getInstance(AES);
    cipher.init(Cipher.DECRYPT_MODE, secretKey);
    byte[] decodedEncryptedData = Base64.getDecoder().decode(encryptedData);
    byte[] decryptedData = cipher.doFinal(decodedEncryptedData);
    return new String(decryptedData);
  }
}
