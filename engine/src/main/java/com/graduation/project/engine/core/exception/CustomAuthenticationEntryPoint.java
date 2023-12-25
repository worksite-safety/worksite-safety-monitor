package com.graduation.project.engine.core.exception;

import com.google.gson.Gson;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashMap;
import java.util.Map;

public class CustomAuthenticationEntryPoint  implements AuthenticationEntryPoint {
    Logger logger = LoggerFactory.getLogger(CustomAuthenticationEntryPoint.class);
    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response, AuthenticationException authException) throws IOException, ServletException {
        response.setContentType("application/json;charset=UTF-8");
        response.setStatus(403);
        ArrayList<Map> arrayOfMap = new ArrayList<>();
        Map<String, String> map = new HashMap<>();
        map.put("code", "403");
        map.put("statusMessage", "Forbidden");
        map.put("message", "Access denied");
        map.put("timestamp", new Date().toString());
        map.put("path", request.getRequestURI());
        arrayOfMap.add(map);
        response.getWriter().write(new Gson().toJson(arrayOfMap));
    }
}
