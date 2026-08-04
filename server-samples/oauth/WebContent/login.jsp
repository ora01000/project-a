<%@ page import="java.lang.*" %>
<%@ page import="java.io.*" %>
<%@ page import="java.util.*" %>
<%@ page import="java.net.*" %>
<%@ page import="javax.net.ssl.*" %>
<%@ page import="java.security.cert.*" %>
<%@ page import="java.security.cert.*" %>
<%@ page import="com.Sha512" %>
<%@ page import="org.owasp.validator.html.*" %>
<%@ page import="org.apache.xml.serialize.HTMLSerializer" %>
<%@ page import="net.sf.json.*" %>

<%
	Policy policy = Policy.getInstance("/deployments/ROOT/antisamy.xml");
	AntiSamy antiSamy = new AntiSamy();

	String[] values = null;

    String authorization = request.getHeader("Authorization");
   // System.out.println(authorization);
    if(authorization != null && authorization.toLowerCase().startsWith("basic")) {
        String base64Credentials = authorization.substring("Basic".length()).trim();
        byte[] credDecoded = Base64.getDecoder().decode(base64Credentials);
        String credentials = new String(credDecoded, "UTF-8");

        values = credentials.split(":", 2);
    }

    if (values != null) {
	    String uname = values[0];
	    String passSha512 = values[1];
	    
	    uname = antiSamy.scan(uname, policy).getCleanHTML(); // XSS 방지
	    passSha512 = antiSamy.scan(passSha512, policy).getCleanHTML(); // XSS 방지
	    
	    // Sha512 암호화
	 	Sha512 sha512 = new Sha512();
		try {
			passSha512 = sha512.SHA_512(passSha512, 128);
			
		} catch (Exception e) {
			e.printStackTrace();
		}	
	  
	    String client_id = System.getenv("OAUTH_CLIENT_ID");
	    String client_secret = System.getenv("OAUTH_CLIENT_SECRET");
	    String autype = System.getenv("OAUTH_AUTH_TYPE");
	    String scope = System.getenv("OAUTH_SCOPE");
	    String grant_type = System.getenv("OAUTH_GRANT_TYPE");
	    String oauth_url = System.getenv("OAUTH_URL");

	/*
	    StringBuffer cmdStr = new StringBuffer("curl -X POST ")
	        .append("--header 'Content-Type: application/x-www-form-urlencoded' ")
	        .append("--header 'Accept: application/json' ")
	        .append("-d 'grant_type=").append(grant_type)
	        .append("&client_id=").append(client_id)
	        .append("&client_secret=").append(client_secret)
	        .append("&password=").append(password)
	        .append("&scope=").append(scope)
	        .append("&auth_type=").append(auth_type)
	        .append("&user_id=").append(username).append("' ")
	        .append("'").append(oauth_url).append("' -k");
	
	    // curl -X POST --header 'Content-Type: application/x-www-form-urlencoded' --header 'Accept: application/json' -d 'grant_type=password&client_id=0f64e652-134c-45e8-b80f-435b2d715b08&client_secret=fK6vP8dE3xL5mX4qP3nX8qW5xC7fX4mW7nH4lS5yW4yI1rG6pD&scope=EA&auth_type=IM&password=05e4f7a100ece6900a043a3102ee80991bfe3324c512f8a8d49f610df8044ebb5da9326bc83e01847d91d7dc13dda50d8b2ccd9fa5509b516701850d18f6a11c&user_id=mslim2' 'https://devapi.lguplus.co.kr/uplus/intuser/oauth2/token' -k
	
	*/
	    String urly = oauth_url;
	    URL obj = new URL(urly);
	    HttpsURLConnection con = (HttpsURLConnection) obj.openConnection();
	
	    con.setRequestMethod("POST");
	    con.setRequestProperty("Content-Type","application/x-www-form-urlencoded");
	    con.setRequestProperty("Accept", "application/json");
	
	    con.setDoOutput(true);
	    con.setDoInput(true);
	    con.setUseCaches(false);
	    con.setHostnameVerifier(new HostnameVerifier() {
	
	        @Override
	        public boolean verify(String hostname, SSLSession session) {
	            return true;
	        }
	    });
        
        
	    // SSL setting
	    SSLContext ctx = SSLContext.getInstance("TLS");
	    ctx.init(null, new TrustManager[]{
	        new javax.net.ssl.X509TrustManager() {
	
	            @Override
	            public X509Certificate[] getAcceptedIssuers() {
	                return null;
	            }
	
	            @Override
	            public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
	            }
	
	            @Override
	            public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
	            }
	        }
	    }, null);
	    con.setSSLSocketFactory(ctx.getSocketFactory());
	
	
	    DataOutputStream wr = new DataOutputStream(con.getOutputStream());
	    String urlTxt = "grant_type=" + grant_type +
						"&client_id=" + client_id +
						"&client_secret=" + client_secret +
						"&scope=" + scope +
						"&auth_type=" + autype +
						"&user_id=" + uname +
						"&password=" + passSha512;
	    
	    wr.writeBytes(urlTxt);
	    wr.flush();
	    wr.close();

	    int responseCode = con.getResponseCode();
            
            java.text.SimpleDateFormat sdf = new java.text.SimpleDateFormat("HH:mm:ss");
	    System.out.println(sdf.format(new java.util.Date()) + " Response Code : " + responseCode);
	    System.out.println(sdf.format(new java.util.Date()) + " Response Msg: " + con.getResponseMessage());

	    if(responseCode == 200)
	    {
	        BufferedReader iny = new BufferedReader(new InputStreamReader(con.getInputStream()));
	        String output;
	        StringBuffer res= new StringBuffer();

	        while ((output = iny.readLine()) != null) {
      //          System.out.println(output + "---");
	            res.append(output);
	        }
	        iny.close();
		System.out.println(sdf.format(new java.util.Date()) + " Output: " + res.toString());
	
       //     System.out.println("--step6--");
	        //printing result from response
	        // login succcess
	        // String retval = "{\"sub\":\"" + uname + "\"}";
	        // CleanResults cleanResults = antiSamy.scan(retval, policy);
		    response.setContentType("application/json"); 
		    JSONObject jsonObj = new JSONObject();
		    uname = antiSamy.scan(uname, policy).getCleanHTML(); // XSS 방지
       //     System.out.println("--step7--");
		    jsonObj.put("sub", uname);
       //     System.out.println("--step8--");
		    response.getWriter().write(jsonObj.toString());
       //     System.out.println("--step9--");
	      System.out.println(sdf.format(new java.util.Date()) + " [INFO] User [" + uname + "] is logged in OpenShift Container Platform successfully");
	    }
            else
            {
	      System.out.println(sdf.format(new java.util.Date()) + " [ERR] User [" + uname + "] failed to login");
            }
    }
%>
