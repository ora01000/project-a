<%@ page import="java.lang.*" %>
<%@ page import="java.io.*" %>
<%@ page import="java.util.*" %>
<%@ page import="java.net.*" %>
<%@ page import="javax.net.ssl.*" %>
<%@ page import="java.security.cert.*" %>
<%@ page import="org.owasp.validator.html.*" %>
<%@ page import="org.apache.xml.serialize.HTMLSerializer" %>
<%@ page import="net.sf.json.*" %>

<%!
	private static String enc(String value) throws UnsupportedEncodingException {
		return URLEncoder.encode(value == null ? "" : value, "UTF-8");
	}

	private static void writeJsonError(
		HttpServletResponse response,
		int status,
		String error,
		String message
	) throws IOException {
		response.resetBuffer();
		response.setStatus(status);
		response.setContentType("application/json; charset=UTF-8");
		response.setCharacterEncoding("UTF-8");
		JSONObject body = new JSONObject();
		body.put("error", error == null ? "error" : error);
		body.put("message", message == null ? "" : message);
		response.getWriter().write(body.toString());
		response.flushBuffer();
	}
%>
<%
	java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("HH:mm:ss");
	String unameForLog = "-";

	try {
		Policy policy = Policy.getInstance("/deployments/ROOT/antisamy.xml");
		AntiSamy antiSamy = new AntiSamy();

		String[] values = null;
		String authorization = request.getHeader("Authorization");
		if (authorization != null && authorization.toLowerCase().startsWith("basic")) {
			String base64Credentials = authorization.substring("Basic".length()).trim();
			byte[] credDecoded = Base64.getDecoder().decode(base64Credentials);
			String credentials = new String(credDecoded, "UTF-8");
			values = credentials.split(":", 2);
		}

		if (values == null || values.length < 2) {
			System.out.println(sdf.format(new java.util.Date())
				+ " [ERR] Missing or invalid Basic Authorization header");
			writeJsonError(response, 401, "invalid_request", "Basic Authorization required");
			return;
		}

		String uname = values[0];
		String password = values[1];
		uname = antiSamy.scan(uname, policy).getCleanHTML();
		password = antiSamy.scan(password, policy).getCleanHTML();
		unameForLog = uname;

		// Auth-provider policy: send password in plaintext (no SHA-512).
		String client_id = System.getenv("OAUTH_CLIENT_ID");
		String client_secret = System.getenv("OAUTH_CLIENT_SECRET");
		String autype = System.getenv("OAUTH_AUTH_TYPE");
		String scope = System.getenv("OAUTH_SCOPE");
		String grant_type = System.getenv("OAUTH_GRANT_TYPE");
		String oauth_url = System.getenv("OAUTH_URL");

		if (oauth_url == null || oauth_url.trim().isEmpty()) {
			System.out.println(sdf.format(new java.util.Date())
				+ " [ERR] OAUTH_URL is not configured");
			writeJsonError(response, 500, "server_error", "OAUTH_URL is not configured");
			return;
		}

		URL obj = new URL(oauth_url.trim());
		HttpsURLConnection con = (HttpsURLConnection) obj.openConnection();

		con.setRequestMethod("POST");
		con.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
		con.setRequestProperty("Accept", "application/json");
		con.setDoOutput(true);
		con.setDoInput(true);
		con.setUseCaches(false);
		con.setConnectTimeout(15000);
		con.setReadTimeout(30000);
		con.setHostnameVerifier(new HostnameVerifier() {
			@Override
			public boolean verify(String hostname, SSLSession session) {
				return true;
			}
		});

		// SSL setting — TLS 1.2+ required for APIM
		// Use SSLSocketFactory only (HttpsURLConnection has no setSSLParameters).
		SSLContext ctx = SSLContext.getInstance("TLSv1.2");
		ctx.init(null, new TrustManager[]{
			new javax.net.ssl.X509TrustManager() {
				@Override
				public X509Certificate[] getAcceptedIssuers() {
					return new X509Certificate[0];
				}

				@Override
				public void checkServerTrusted(X509Certificate[] chain, String authType)
					throws CertificateException {
				}

				@Override
				public void checkClientTrusted(X509Certificate[] chain, String authType)
					throws CertificateException {
				}
			}
		}, null);
		con.setSSLSocketFactory(ctx.getSocketFactory());

		String urlTxt = "grant_type=" + enc(grant_type)
			+ "&client_id=" + enc(client_id)
			+ "&client_secret=" + enc(client_secret)
			+ "&scope=" + enc(scope)
			+ "&auth_type=" + enc(autype)
			+ "&user_id=" + enc(uname)
			+ "&password=" + enc(password);

		DataOutputStream wr = new DataOutputStream(con.getOutputStream());
		wr.writeBytes(urlTxt);
		wr.flush();
		wr.close();

		int responseCode = con.getResponseCode();
		System.out.println(sdf.format(new java.util.Date()) + " Response Code : " + responseCode);
		System.out.println(sdf.format(new java.util.Date()) + " Response Msg: " + con.getResponseMessage());

		if (responseCode == 200) {
			BufferedReader iny = new BufferedReader(new InputStreamReader(con.getInputStream(), "UTF-8"));
			String output;
			StringBuffer res = new StringBuffer();
			while ((output = iny.readLine()) != null) {
				res.append(output);
			}
			iny.close();
			System.out.println(sdf.format(new java.util.Date()) + " Output: " + res.toString());

			response.setStatus(200);
			response.setContentType("application/json; charset=UTF-8");
			response.setCharacterEncoding("UTF-8");
			JSONObject jsonObj = new JSONObject();
			uname = antiSamy.scan(uname, policy).getCleanHTML();
			jsonObj.put("sub", uname);
			response.getWriter().write(jsonObj.toString());
			System.out.println(sdf.format(new java.util.Date())
				+ " [INFO] User [" + uname + "] is logged in OpenShift Container Platform successfully");
		} else {
			InputStream errStream = con.getErrorStream();
			if (errStream != null) {
				BufferedReader ery = new BufferedReader(new InputStreamReader(errStream, "UTF-8"));
				StringBuilder errBody = new StringBuilder();
				String line;
				while ((line = ery.readLine()) != null) {
					errBody.append(line);
				}
				ery.close();
				if (errBody.length() > 0) {
					System.out.println(sdf.format(new java.util.Date())
						+ " Upstream error body: " + errBody.toString());
				}
			}
			System.out.println(sdf.format(new java.util.Date())
				+ " [ERR] User [" + uname + "] failed to login");
			// OKD BasicAuth IdP: failure must be non-200 (never empty 200 / HTML).
			writeJsonError(response, 401, "access_denied", "upstream authentication failed");
		}
	} catch (Throwable t) {
		// Prevent container HTML error pages — oauth-openshift expects JSON or empty non-200.
		System.out.println(sdf.format(new java.util.Date())
			+ " [ERR] User [" + unameForLog + "] login exception: "
			+ t.getClass().getName() + ": " + t.getMessage());
		t.printStackTrace(System.out);
		try {
			writeJsonError(response, 500, "server_error", "identity provider internal error");
		} catch (Exception writeFail) {
			System.out.println(sdf.format(new java.util.Date())
				+ " [ERR] Failed to write JSON error response: " + writeFail.getMessage());
			response.setStatus(500);
		}
	}
%>
