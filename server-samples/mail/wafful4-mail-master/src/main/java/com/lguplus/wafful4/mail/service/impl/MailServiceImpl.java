/**
 *------------------------------------------------------------------------------
 * @Project : LGU+ WAFFUL-2.0 Project
 * @Package : com.lguplus.wafful.framework.mail.Sender
 * @Source  : MailService.java
 * @Desc    :
 *
 * Copyright ⓒ 2019 LG U+ All rights reserved
 *------------------------------------------------------------------------------
 *                  변         경         사         항
 *------------------------------------------------------------------------------
 *    VER  	DATE        AUTHOR      DESCRIPTION
 * -----------------------------------------------------------------------------
 * 	1. 0    2019. 8. 28.  mks766736       최초 프로그램 작성
 *------------------------------------------------------------------------------
 */
package com.lguplus.wafful4.mail.service.impl;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

import com.lguplus.wafful4.core.model.DataMap;
import com.lguplus.wafful4.mail.policy.MailPolicyService;
import com.lguplus.wafful4.mail.service.MailService;
import com.lguplus.wafful4.mail.service.builder.MailBuilder;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeUtility;
import lombok.extern.slf4j.Slf4j;



/**
 * <PRE>
 * com.lguplus.wafful.framework.mail.Sender.MailService.java
 * </PRE>
 *
 * @Author mks766736
 * @Date 2019. 8. 28. 오후 1:39:44
 * @Version 1.0
 * @Tag
 */
@Slf4j
public class MailServiceImpl implements MailService {

	private JavaMailSender emailSender;
	private MailBuilder mailBuilder;
	private MailPolicyService mailPolicyService;

	/**
	 * 메일 발송
	 *
	 * <PRE>
	 *  Class Name    : MailService
	 *  Comment       : 초기설명
	 * </PRE>
	 *
	 * @Author mks766736
	 * @Date 2019. 8. 28. 오후 1:54:52
	 * @Tag @param emailSender
	 * @Tag @param templateEngine
	 * @Tag @param mailBuilder
	 * @Tag @param mailPolicyService
	 */
	public MailServiceImpl(JavaMailSender emailSender, MailBuilder mailBuilder, MailPolicyService mailPolicyService) {
		this.emailSender = emailSender;
		this.mailBuilder = mailBuilder;
		this.mailPolicyService = mailPolicyService;
	}

	/**
	 * 메일 발송실행
	 *
	 * <PRE>
	 *  Class Name    : MailService
	 *  Method Name   : sendMessage
	 *  Comment       : 초기설명
	 *  예> sendMessage("default", "제목", dataMap)
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
	@Override
	public void sendMailByPolicy(String policy, String subject, String to, String from, DataMap dataMap)
			throws MessagingException, IOException {

		MimeMessage message = emailSender.createMimeMessage();
		MimeMessageHelper helper = new MimeMessageHelper(message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
				StandardCharsets.UTF_8.name());

		String[] placeholders = mailPolicyService.getPlaceHolderArray(policy);
		String template = mailPolicyService.getTemplate(policy);
		String html = mailBuilder.build(placeholders, template, dataMap);

		helper.setTo(to);
		helper.setFrom(from);
		helper.setSubject(subject);
		helper.setText(html, true);
		emailSender.send(message);
	}

	@Override
	public void sendMailByPolicy(String policy, String subject, String to, String from, String personal, DataMap dataMap)
			throws MessagingException, IOException {

		MimeMessage message = emailSender.createMimeMessage();
		MimeMessageHelper helper = new MimeMessageHelper(message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
				StandardCharsets.UTF_8.name());

		String[] placeholders = mailPolicyService.getPlaceHolderArray(policy);
		String template = mailPolicyService.getTemplate(policy);
		String html = mailBuilder.build(placeholders, template, dataMap);

		helper.setTo(to);
		helper.setFrom(from, personal);
		helper.setSubject(subject);
		helper.setText(html, true);
		emailSender.send(message);
	}

	@Override
	public void sendMailWithContent(String subject, String template, String to, String from, String[] placeholders,
			DataMap dataMap) throws MessagingException, IOException {

		MimeMessage message = emailSender.createMimeMessage();
		MimeMessageHelper helper = new MimeMessageHelper(message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
				StandardCharsets.UTF_8.name());

		String html = mailBuilder.build(placeholders, template, dataMap);

		helper.setTo(to);
		helper.setFrom(from);
		helper.setSubject(subject);
		helper.setText(html, true);
		emailSender.send(message);
	}

	@Override
	public void sendMailByTemplate(String subject, String template, String to, String from, String personal,
			String[] placeholders, DataMap dataMap) throws MessagingException, IOException {

		MimeMessage message = emailSender.createMimeMessage();
		MimeMessageHelper helper = new MimeMessageHelper(message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
				StandardCharsets.UTF_8.name());

		String html = mailBuilder.build(placeholders, template, dataMap);

		helper.setTo(to);
		helper.setFrom(from, personal);
		helper.setSubject(subject);
		helper.setText(html, true);
		emailSender.send(message);
	}

	@Override
	public void sendMailByTemplate(String subject, String html, String to, String from)
			throws MessagingException, IOException {

		MimeMessage message = emailSender.createMimeMessage();
		MimeMessageHelper helper = new MimeMessageHelper(message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
				StandardCharsets.UTF_8.name());

		helper.setTo(to);
		helper.setFrom(from);
		helper.setSubject(subject);
		helper.setText(html, true);

		emailSender.send(message);
	}

	@Override
	public void sendMailWithContent(String subject, String html, String to, String from, String personal)
			throws MessagingException, IOException {

		MimeMessage message = emailSender.createMimeMessage();
		MimeMessageHelper helper = new MimeMessageHelper(message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
				StandardCharsets.UTF_8.name());

		helper.setTo(to);
		helper.setFrom(from, personal);
		helper.setSubject(subject);
		helper.setText(html, true);

		emailSender.send(message);
	}

	/**
	 * 대랑 메일 발송
	 *
	 * <PRE>
	 *  Class Name    : MailService
	 *  Method Name   : sendMessage
	 *  Comment       : 초기설명
	 *  예> sendMessage("default", "제목", dataMapList)
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
	@Override
	public void sendMailByPolicy(String policy, String subject, List<String> toList, String from, List<DataMap> dataMapList)
			throws MessagingException, IOException {
		for (int i = 0; i < toList.size(); i++) {
			DataMap dataMap = dataMapList.get(i);
			String to = toList.get(i);
			sendMailByPolicy(policy, subject, to, from, dataMap);
		}
	}

	@Override
	public void sendMailWithContent(String subject, String template, List<String> toList, String from, String[] placeholders,
			List<DataMap> dataMapList) throws MessagingException, IOException {
		for (int i = 0; i < toList.size(); i++) {
			DataMap dataMap = dataMapList.get(i);
			String to = toList.get(i);
			sendMailWithContent(subject, template, to, from, placeholders, dataMap);
		}
	}

	@Override
	public void sendMailByTemplate(String subject, String html, List<String> toList, String from)
			throws MessagingException, IOException {
		for (String to : toList) {
			sendMailByTemplate(subject, html, to, from);
		}
	}

	@Override
	public void sendMailByPolicy(String policy, String subject, List<String> toList, String from, String personal,
			List<DataMap> dataMapList) throws MessagingException, IOException {
		for (int i = 0; i < toList.size(); i++) {
			DataMap dataMap = dataMapList.get(i);
			String to = toList.get(i);
			sendMailByPolicy(policy, subject, to, from, personal, dataMap);
		}
	}

	@Override
	public void sendMailByTemplate(String subject, String template, List<String> toList, String from, String personal,
			String[] placeholders, List<DataMap> dataMapList) throws MessagingException, IOException {
		for (int i = 0; i < toList.size(); i++) {
			DataMap dataMap = dataMapList.get(i);
			String to = toList.get(i);
			sendMailByTemplate(subject, template, to, from, personal, placeholders, dataMap);
		}
	}

	@Override
	public void sendMailWithContent(String subject, String html, List<String> toList, String from, String personal)
			throws MessagingException, IOException {
		for (String to : toList) {
			sendMailWithContent(subject, html, to, from, personal);
		}
	}
	
	@Override
	public void sendMail(String subject, String html, List<String> toList, String from, String personal, List<String> ccList, List<String> bccList,
    		List<String> filenameList, List<File> attachFileList) throws MessagingException, IOException {

		MimeMessage message = emailSender.createMimeMessage();
		MimeMessageHelper helper = new MimeMessageHelper(message, MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
				StandardCharsets.UTF_8.name());

		if (toList != null && toList.size() > 0) {
			helper.setTo(toList.toArray(new String[toList.size()]));
		}

		if (personal != null) {
			helper.setFrom(from, personal);
		}
		else {
			helper.setFrom(from);
		}

		if (ccList != null && ccList.size() > 0) {
			helper.setCc(ccList.toArray(new String[ccList.size()]));
		}

		if (bccList != null && bccList.size() > 0) {
			helper.setBcc(bccList.toArray(new String[bccList.size()]));
		}
		
		helper.setSubject(subject);
		helper.setText(html, true);
		
		if (filenameList != null && attachFileList != null 
			&& filenameList.size() > 0 && attachFileList.size() > 0) {
			// 파일명 리스트와 첨부파일객체 리스트의 길이가 다른 경우
			if (filenameList.size() != attachFileList.size()) {
				log.error("Cannot attach file(s). filenameList and attachFileList size unmatch. filenameList:{}, attachFileList:{}", filenameList.size(), attachFileList.size());
			}
			else {
				for (int i = 0; i < filenameList.size(); i++) {
					helper.addAttachment(MimeUtility.encodeWord(filenameList.get(i)), attachFileList.get(i));
				}
			}
		}

		emailSender.send(message);
	}


}
