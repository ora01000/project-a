package com.lguplus.wafful4.mail.application.setting;

import org.springframework.boot.context.properties.ConfigurationProperties;

import lombok.Data;
import lombok.NoArgsConstructor;
import lombok.ToString;

@Data
@ToString
@NoArgsConstructor
@ConfigurationProperties(prefix = WaffulMailProperties.PREFIX, ignoreUnknownFields = false)
public class WaffulMailProperties {

    public static final String PREFIX = "wafful.mail";

    private boolean enabled;
    private String host;
    private int port;
    private int socketPort;
    private boolean auth;
    private boolean startTls;
    private boolean startTlsRequired;
    private boolean fallback;
    private String username;
    private String password;
    private String templatePrefix;
    private String templateSuffix;
}
