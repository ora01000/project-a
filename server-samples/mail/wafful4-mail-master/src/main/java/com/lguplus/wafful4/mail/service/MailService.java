/**
 *------------------------------------------------------------------------------
 * @Project : LGU+ WAFFUL-2.0 Project
 * @Package : com.lguplus.wafful.framework.mail
 * @Source  : MailService.java
 * @Desc    :
 *
 * Copyright ⓒ 2019 LG U+ All rights reserved
 *------------------------------------------------------------------------------
 *                  변         경         사         항
 *------------------------------------------------------------------------------
 *    VER  	DATE        AUTHOR      DESCRIPTION
 * -----------------------------------------------------------------------------
 * 	1. 0    2019. 9. 4.  mks766736       최초 프로그램 작성
 *------------------------------------------------------------------------------
 */
package com.lguplus.wafful4.mail.service;

import java.io.File;
import java.io.IOException;
import java.util.List;

import com.lguplus.wafful4.core.model.DataMap;

import jakarta.mail.MessagingException;


/**
 * <PRE>
 * com.lguplus.wafful.framework.mail.MailService.java
 * </PRE>
 *
 * @Author mks766736
 * @Date 2019. 9. 4. 오후 1:45:22
 * @Version 1.0
 * @Tag
 */
public interface MailService {

    /**
     * 메일 발송실행
     *
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByPolicy
     *  Comment       : 단건 메일 발송 - 정책
     *  예> sendMessage("default", "사용자 등록", to, from, dataMap)
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 8. 28. 오후 1:55:10
     * @Tag @param policy
     * @Tag @param subject
     * @Tag @param dataMap
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    public void sendMailByPolicy(String policy, String subject, String to, String from, DataMap dataMap)
            throws MessagingException, IOException;

    /**
     * 대랑 메일 발송
     *
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByPolicy
     *  Comment       : 대량 메일 발송 - 정책
     *  예> sendMessage("default", "사용자 등록",to 리스트, from,  dataMapList)
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 8. 28. 오후 1:56:21
     * @Tag @param policy
     * @Tag @param subject
     * @Tag @param dataMapList
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    public void sendMailByPolicy(String policy, String subject, List<String> to, String from, List<DataMap> dataMapList)
            throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByTemplate
     *  Comment       : 단건 메일 발송 - html
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 10. 23. 오전 10:20:04
     * @Tag @param subject
     * @Tag @param html
     * @Tag @param to
     * @Tag @param from
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    public void sendMailByTemplate(String subject, String html, String to, String from)
            throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByTemplate
     *  Comment       : 대량 메일 발송 - html
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 10. 23. 오전 10:26:07
     * @Tag @param subject
     * @Tag @param html
     * @Tag @param toList
     * @Tag @param from
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailByTemplate(String subject, String html, List<String> toList, String from)
            throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailWithContent
     *  Comment       : 단건 메일 발송 - 템플릿 컨텐츠
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 10. 24. 오전 9:59:06
     * @Tag @param subject
     * @Tag @param template
     * @Tag @param to
     * @Tag @param from
     * @Tag @param placeholders
     * @Tag @param dataMap
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    public void sendMailWithContent(String subject, String template, String to, String from, String[] placeholders,
            DataMap dataMap) throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailWithContent
     *  Comment       : 대량 메일 발송 - 템플릿 컨텐츠
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 10. 24. 오전 10:01:28
     * @Tag @param subject
     * @Tag @param template
     * @Tag @param toList
     * @Tag @param from
     * @Tag @param placeholders
     * @Tag @param dataMapList
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailWithContent(String subject, String template, List<String> toList, String from, String[] placeholders,
            List<DataMap> dataMapList) throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByPolicy
     *  Comment       : 초기설명
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 11. 9. 오전 11:51:39
     * @Tag @param policy
     * @Tag @param subject
     * @Tag @param to
     * @Tag @param from
     * @Tag @param person
     * @Tag @param dataMap
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailByPolicy(String policy, String subject, String to, String from, String person, DataMap dataMap)
            throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByTemplate
     *  Comment       : 초기설명
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 11. 9. 오전 11:53:57
     * @Tag @param subject
     * @Tag @param template
     * @Tag @param to
     * @Tag @param from
     * @Tag @param person
     * @Tag @param placeholders
     * @Tag @param dataMap
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailByTemplate(String subject, String template, String to, String from, String person,
            String[] placeholders, DataMap dataMap) throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByContent
     *  Comment       : 초기설명
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 11. 9. 오전 11:57:28
     * @Tag @param subject
     * @Tag @param html
     * @Tag @param to
     * @Tag @param from
     * @Tag @param personal
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailWithContent(String subject, String html, String to, String from, String personal)
            throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByPolicy
     *  Comment       : 초기설명
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 11. 9. 오전 11:59:00
     * @Tag @param policy
     * @Tag @param subject
     * @Tag @param toList
     * @Tag @param from
     * @Tag @param personal
     * @Tag @param dataMapList
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailByPolicy(String policy, String subject, List<String> toList, String from, String personal,
            List<DataMap> dataMapList) throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMailByTemplate
     *  Comment       : 초기설명
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 11. 9. 오전 11:59:04
     * @Tag @param subject
     * @Tag @param template
     * @Tag @param toList
     * @Tag @param from
     * @Tag @param personal
     * @Tag @param placeholders
     * @Tag @param dataMapList
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailByTemplate(String subject, String template, List<String> toList, String from, String personal,
            String[] placeholders, List<DataMap> dataMapList) throws MessagingException, IOException;

    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMessage
     *  Comment       : 초기설명
     * </PRE>
     *
     * @Author mks766736
     * @Date 2019. 11. 9. 오전 11:59:09
     * @Tag @param subject
     * @Tag @param html
     * @Tag @param toList
     * @Tag @param from
     * @Tag @param personal
     * @Tag @throws MessagingException
     * @Tag @throws IOException
     */
    void sendMailWithContent(String subject, String html, List<String> toList, String from, String personal)
            throws MessagingException, IOException;

	
    /**
     * <PRE>
     *  Class Name    : MailService
     *  Method Name   : sendMail
     *  Comment       : 메일전송 관련 모든 인자를 받아서 처리하는 메소드
     * </PRE>
     *
     * @param subject
     * @param html
     * @param to
     * @param from
     * @param personal
     * @param cc
     * @param bcc
     * @param filename
     * @param attachFile
     * @throws MessagingException
     * @throws IOException
     */
    void sendMail(String subject, String html, List<String> toList, String from, String personal, List<String> ccList, List<String> bccList,
    		List<String> filenameList, List<File> attachFileList) throws MessagingException, IOException;
}
