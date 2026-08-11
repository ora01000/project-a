/**
 *------------------------------------------------------------------------------
 * @Project : LGU+ WAFFUL-2.0 Project
 * @Package : com.lguplus.wafful.framework.mail.builder
 * @Source  : MailContentBuilder.java
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
package com.lguplus.wafful4.mail.service.builder;

import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

import com.lguplus.wafful4.core.model.DataMap;

/**
 * <PRE>
 * com.lguplus.wafful.framework.mail.builder.MailContentBuilder.java
 * </PRE>
 *
 * @Author mks766736
 * @Date 2019. 8. 28. 오후 1:17:07
 * @Version 1.0
 * @Tag
 */
public class MailBuilder {

	private TemplateEngine templateEngine;

	public MailBuilder(TemplateEngine templateEngine) {
		this.templateEngine = templateEngine;
	}

	public String build(String[] placeholders, String template, DataMap dataMap) {
		Context context = new Context();
		for (String s : placeholders) {
			s = s.trim();
			context.setVariable(s, dataMap.get(s));
		}
		return templateEngine.process(template, context);
	}
}
