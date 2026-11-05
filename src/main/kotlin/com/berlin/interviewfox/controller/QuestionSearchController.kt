package com.berlin.interviewfox.controller

import com.baomidou.mybatisplus.extension.plugins.pagination.Page
import com.berlin.interviewfox.common.BaseResponse
import com.berlin.interviewfox.common.ResultUtils
import com.berlin.interviewfox.model.dto.question.QuestionQueryRequest
import com.berlin.interviewfox.model.vo.QuestionVO
import com.berlin.interviewfox.service.QuestionSearchService
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RequestParam
import org.springframework.web.bind.annotation.RestController
import javax.servlet.http.HttpServletRequest

@RestController
@RequestMapping("/question")
class QuestionSearchController(private val questionSearchService: QuestionSearchService) {

    @PostMapping("/list/page/vo")
    fun listQuestionVOByPage(
        @RequestBody(required = false) query: QuestionQueryRequest?,
        @RequestParam(defaultValue = "mysql") engine: String,
        request: HttpServletRequest
    ): BaseResponse<Page<QuestionVO>> = ResultUtils.success(questionSearchService.search(query, engine, request))
}
