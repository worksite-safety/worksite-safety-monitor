package com.graduation.project.engine.core;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@Component
public class PasswordService {

  private static final String AES = "AES";
  private static final String secretKey = "5A7134743777217A";

  private BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();

  public String hashPassword(String password) {
    return passwordEncoder.encode(password);
  }

  public boolean verifyPassword(String rawPassword, String hashedPassword) {
    return passwordEncoder.matches(rawPassword, hashedPassword);
  }

  public String encrypt(String data) throws Exception {
    Cipher cipher = Cipher.getInstance(AES);
    SecretKey secretKeySpec = new SecretKeySpec(secretKey.getBytes(StandardCharsets.UTF_8), AES);
    cipher.init(Cipher.ENCRYPT_MODE, secretKeySpec);
    byte[] encryptedData = cipher.doFinal(data.getBytes());
    return Base64.getEncoder().encodeToString(encryptedData);
  }

  public String decrypt(String encryptedData) throws Exception {
    Cipher cipher = Cipher.getInstance(AES);
    SecretKey secretKeySpec = new SecretKeySpec(secretKey.getBytes(StandardCharsets.UTF_8), AES);
    cipher.init(Cipher.DECRYPT_MODE, secretKeySpec);
    byte[] decodedEncryptedData = Base64.getDecoder().decode(encryptedData);
    byte[] decryptedData = cipher.doFinal(decodedEncryptedData);
    return new String(decryptedData);
  }
}
