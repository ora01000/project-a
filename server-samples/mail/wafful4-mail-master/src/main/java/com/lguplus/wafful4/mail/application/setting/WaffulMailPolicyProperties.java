package com.lguplus.wafful4.mail.application.setting;

import java.util.HashMap;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.ToString;

@Data
@NoArgsConstructor
@ConfigurationProperties(prefix = WaffulMailPolicyProperties.PREFIX, ignoreUnknownFields = true)
public class WaffulMailPolicyProperties {

    public static final String PREFIX = "wafful.data.policy";

    private Map<String, TemplateProperties> mail = new HashMap<String, TemplateProperties>();
    
    @Data
    @ToString
    @NoArgsConstructor
    public static class TemplateProperties {
        private String placeholder = "name, signature, location, userList";
        private String template = "/default";
    }
}
