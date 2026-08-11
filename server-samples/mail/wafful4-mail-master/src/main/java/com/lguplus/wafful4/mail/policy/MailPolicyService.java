/*******************************************************************************
 *
 * ------------------------------------------------------------------------------
 *  @Project : LGU+ WAFFUL-2.0 Project
 *  @Package :
 *  @Source  : MailPolicyService.java
 *  @Desc    :
 *
 *  Copyright ⓒ 2019 LG U+ All rights reserved
 * ------------------------------------------------------------------------------
 *                   변         경         사         항
 * ------------------------------------------------------------------------------
 *     VER  	DATE        AUTHOR      DESCRIPTION
 *  -----------------------------------------------------------------------------
 *  	1. 0    .   mks766736       최초 프로그램 작성
 * ------------------------------------------------------------------------------
 *
 ******************************************************************************/
package com.lguplus.wafful4.mail.policy;

import com.lguplus.wafful4.core.constants.CommonConstants;
import com.lguplus.wafful4.core.utils.WaffulStringUtils;
import com.lguplus.wafful4.mail.application.setting.WaffulMailPolicyProperties;
import com.lguplus.wafful4.mail.application.setting.WaffulMailPolicyProperties.TemplateProperties;

import lombok.Data;

@Data
public class MailPolicyService {

    /**
     * 페이징 정책
     */
    private WaffulMailPolicyProperties mailPolicy = new WaffulMailPolicyProperties();

    public MailPolicyService(WaffulMailPolicyProperties mailPolicy) {
        this.mailPolicy = mailPolicy;
    }

    public String getPlaceHolder() {
        return getPlaceHolder(CommonConstants.POLICY_DEFAULT);
    }

    public String getTemplate() {
        return getTemplate(CommonConstants.POLICY_DEFAULT);
    }

    public String getPlaceHolder(String policy) {
    	TemplateProperties mailTemplate = mailPolicy.getMail().get(policy);
        
        if (mailTemplate == null)
            return null;
        return WaffulStringUtils.getString(mailTemplate.getPlaceholder());
    }

    public String[] getPlaceHolderArray(String policy) {
        String sPlaceHolder = getPlaceHolder(policy);
        return WaffulStringUtils.split(sPlaceHolder, ",");
    }

    public String getTemplate(String policy) {
        TemplateProperties mailTemplate = mailPolicy.getMail().get(policy);
        if (mailTemplate == null)
            return null;
        return WaffulStringUtils.getString(mailTemplate.getTemplate());
    }

}
