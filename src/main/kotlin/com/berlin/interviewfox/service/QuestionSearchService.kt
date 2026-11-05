package com.berlin.interviewfox.service

import com.baomidou.mybatisplus.extension.plugins.pagination.Page
import com.berlin.interviewfox.common.ErrorCode
import com.berlin.interviewfox.constant.CommonConstant.SORT_ORDER_ASC
import com.berlin.interviewfox.exception.BusinessException
import com.berlin.interviewfox.model.dto.question.QuestionQueryRequest
import com.berlin.interviewfox.model.entity.Question
import com.berlin.interviewfox.model.vo.QuestionVO
import com.berlin.interviewfox.service.search.QuestionSearchIndex
import org.springframework.stereotype.Service
import javax.servlet.http.HttpServletRequest

@Service
class QuestionSearchService(
    private val questionService: QuestionService,
    private val searchIndex: QuestionSearchIndex?
) {

    fun search(query: QuestionQueryRequest?, engine: String, request: HttpServletRequest): Page<QuestionVO> {
        val criteria = query ?: throw BusinessException(ErrorCode.PARAMS_ERROR, "请求体不能为空")
        val current = criteria.current.takeIf { it >= 1 }
            ?: throw BusinessException(ErrorCode.PARAMS_ERROR, "页码必须大于等于 1")
        val pageSize = criteria.pageSize.takeIf { it in 1..MAX_PAGE_SIZE }
            ?: throw BusinessException(ErrorCode.PARAMS_ERROR, "每页条数必须在 1 到 $MAX_PAGE_SIZE 之间")

        // An explicit JSON null can overwrite the Java DTO's default.
        criteria.sortOrder = criteria.sortOrder ?: SORT_ORDER_ASC
        val page = when (engine) {
            "mysql" -> questionService.page(
                Page<Question>(current.toLong(), pageSize.toLong()), questionService.getQueryWrapper(criteria)
            )
            "elasticsearch" -> {
                val index = searchIndex
                    ?: throw BusinessException(ErrorCode.OPERATION_ERROR, "Elasticsearch 题目搜索未启用")
                index.search(criteria, current, pageSize)
            }
            else -> throw BusinessException(ErrorCode.PARAMS_ERROR, "engine 必须为 mysql 或 elasticsearch")
        }
        return questionService.getQuestionVOPage(page, request)
    }

    private companion object {
        const val MAX_PAGE_SIZE = 20
    }
}
