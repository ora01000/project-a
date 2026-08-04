package com;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

public class Sha512 {

	public String SHA_512(String inputMessage,int returnSpliteByte) throws NoSuchAlgorithmException {
        MessageDigest md;
        String out = "";

        try {
            md= MessageDigest.getInstance("SHA-512");

            md.update(inputMessage.getBytes());
            byte[] mb = md.digest();

            for (int i = 0; i < mb.length; i++) {
                byte temp = mb[i];
                String s = Integer.toHexString(new Byte(temp));
                while (s.length() < 2) {
                    s = "0" + s;
                }
                s = s.substring(s.length() - 2);
                out += s;
            }

//            if(returnSpliteByte > 0)
//            	System.out.println(out.substring(0,returnSpliteByte));

        } catch (Exception e) {
            System.out.println("ERROR: " + e.getMessage());
        }

        return out;

	}

}
