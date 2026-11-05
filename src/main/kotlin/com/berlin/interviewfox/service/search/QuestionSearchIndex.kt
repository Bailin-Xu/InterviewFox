package com.berlin.interviewfox.service.search

import com.baomidou.mybatisplus.extension.plugins.pagination.Page
import com.berlin.interviewfox.common.ErrorCode
import com.berlin.interviewfox.constant.CommonConstant.SORT_ORDER_ASC
import com.berlin.interviewfox.exception.BusinessException
import com.berlin.interviewfox.model.dto.question.QuestionQueryRequest
import com.berlin.interviewfox.model.entity.Question
import com.fasterxml.jackson.core.type.TypeReference
import com.fasterxml.jackson.databind.ObjectMapper
import org.elasticsearch.ElasticsearchException
import org.elasticsearch.ElasticsearchStatusException
import org.elasticsearch.action.admin.indices.refresh.RefreshRequest
import org.elasticsearch.action.bulk.BulkRequest
import org.elasticsearch.action.delete.DeleteRequest
import org.elasticsearch.action.index.IndexRequest
import org.elasticsearch.action.search.SearchRequest
import org.elasticsearch.client.RequestOptions.DEFAULT
import org.elasticsearch.client.RestHighLevelClient
import org.elasticsearch.client.indices.CreateIndexRequest
import org.elasticsearch.client.indices.GetIndexRequest
import org.elasticsearch.index.query.Operator
import org.elasticsearch.index.query.QueryBuilders
import org.elasticsearch.rest.RestStatus
import org.elasticsearch.search.builder.SearchSourceBuilder
import org.elasticsearch.search.sort.SortOrder
import org.elasticsearch.xcontent.XContentType
import org.slf4j.LoggerFactory
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
import org.springframework.core.io.ClassPathResource
import org.springframework.stereotype.Component
import java.io.IOException

@Component
@ConditionalOnProperty(prefix = "interviewfox.search.elasticsearch", name = ["enabled"], havingValue = "true")
class QuestionSearchIndex(
    private val client: RestHighLevelClient,
    private val objectMapper: ObjectMapper
) {
    @Volatile
    internal var ready = false

    fun search(query: QuestionQueryRequest, current: Int, pageSize: Int): Page<Question> {
        val offset = (current.toLong() - 1) * pageSize
        if (offset + pageSize > MAX_RESULT_WINDOW) {
            throw BusinessException(ErrorCode.PARAMS_ERROR, "Elasticsearch 最多支持分页浏览前 10000 条结果")
        }
        if (!ready) {
            throw BusinessException(ErrorCode.OPERATION_ERROR, "Elasticsearch 题目索引正在同步，请稍后重试")
        }
        val request = SearchRequest(INDEX_NAME).source(buildSearch(query, offset.toInt(), pageSize))
            .allowPartialSearchResults(false)
        try {
            val result = client.search(request, DEFAULT)
            if (result.isTimedOut) {
                throw BusinessException(ErrorCode.OPERATION_ERROR, "Elasticsearch 题目搜索超时")
            }
            val hits = result.hits
            val total = checkNotNull(hits.totalHits) { "Question search did not return a total" }.value
            return Page<Question>(current.toLong(), pageSize.toLong(), total).apply {
                records = hits.hits.map { hit ->
                    val source = hit.sourceAsMap.toMutableMap()
                    source["tags"] = source["tags"]?.let(objectMapper::writeValueAsString)
                    objectMapper.convertValue(source, Question::class.java)
                }
            }
        } catch (failure: IOException) {
            throw searchUnavailable(failure)
        } catch (failure: ElasticsearchException) {
            throw searchUnavailable(failure)
        }
    }

    private fun buildSearch(query: QuestionQueryRequest, offset: Int, pageSize: Int): SearchSourceBuilder {
        val filters = QueryBuilders.boolQuery()
        query.id?.let { filters.filter(QueryBuilders.termQuery("id", it)) }
        query.notId?.let { filters.mustNot(QueryBuilders.termQuery("id", it)) }
        query.userId?.let { filters.filter(QueryBuilders.termQuery("userId", it)) }
        query.tags.orEmpty().forEach { filters.filter(QueryBuilders.termQuery("tags", it)) }
        query.searchText?.takeUnless(String::isBlank)?.let {
            filters.must(
                QueryBuilders.multiMatchQuery(it).field("title", 3f).field("content").operator(Operator.AND)
            )
        }
        listOf("title" to query.title, "content" to query.content, "answer" to query.answer)
            .forEach { (field, text) ->
                text?.takeUnless(String::isBlank)?.let {
                    filters.must(QueryBuilders.matchQuery(field, it).operator(Operator.AND))
                }
            }

        val source = SearchSourceBuilder().query(filters).from(offset).size(pageSize).trackTotalHits(true)
        val sortField = query.sortField?.takeUnless(String::isBlank)
        if (sortField == null) {
            source.sort("_score", SortOrder.DESC)
        } else {
            val field = when (sortField) {
                "title" -> "title.raw"
                "id", "userId", "editTime", "createTime", "updateTime", "isDelete" -> sortField
                else -> throw BusinessException(ErrorCode.PARAMS_ERROR, "Elasticsearch 不支持该排序字段")
            }
            val order = if (query.sortOrder == SORT_ORDER_ASC) SortOrder.ASC else SortOrder.DESC
            source.sort(field, order)
        }
        if (sortField != "id") {
            source.sort("id", SortOrder.ASC)
        }
        return source
    }

    internal fun ensureIndex(): String {
        val request = GetIndexRequest(INDEX_NAME)
        val indices = client.indices()
        val index = try {
            indices.get(request, DEFAULT)
        } catch (failure: ElasticsearchStatusException) {
            if (failure.status() != RestStatus.NOT_FOUND) throw failure
            ready = false
            val mapping = ClassPathResource("elasticsearch/question-index.json").inputStream
                .bufferedReader().use { it.readText() }
            val created = indices.create(CreateIndexRequest(INDEX_NAME).source(mapping, XContentType.JSON), DEFAULT)
            check(created.isAcknowledged) { "Question index creation was not acknowledged" }
            indices.get(request, DEFAULT)
        }
        return checkNotNull(index.getSetting(INDEX_NAME, "index.uuid")) { "Question index has no UUID" }
    }

    internal fun write(questions: Collection<Question>, deletedIds: Collection<Long> = emptyList()) {
        val bulk = BulkRequest()
        questions.forEach { question ->
            val document = mapOf(
                "id" to question.id,
                "title" to question.title,
                "content" to question.content,
                "tags" to question.tags?.takeUnless(String::isBlank)?.let {
                    objectMapper.readValue(it, object : TypeReference<List<String>>() {})
                },
                "answer" to question.answer,
                "userId" to question.userId,
                "editTime" to question.editTime?.time,
                "createTime" to question.createTime?.time,
                "updateTime" to question.updateTime?.time,
                "isDelete" to question.isDelete
            )
            bulk.add(IndexRequest(INDEX_NAME).id(question.id.toString()).source(document))
        }
        deletedIds.forEach { bulk.add(DeleteRequest(INDEX_NAME, it.toString())) }
        if (bulk.numberOfActions() == 0) return

        val response = client.bulk(bulk, DEFAULT)
        check(!response.hasFailures()) { response.buildFailureMessage() }
    }

    internal fun refresh() {
        val response = client.indices().refresh(RefreshRequest(INDEX_NAME), DEFAULT)
        check(response.failedShards == 0) { "Question index refresh failed" }
    }

    private fun searchUnavailable(failure: Exception): BusinessException {
        LOG.warn("Elasticsearch question search failed", failure)
        return BusinessException(ErrorCode.OPERATION_ERROR, "Elasticsearch 题目搜索暂时不可用")
    }

    private companion object {
        const val INDEX_NAME = "interviewfox-question-v1"
        const val MAX_RESULT_WINDOW = 10_000
        val LOG = LoggerFactory.getLogger(QuestionSearchIndex::class.java)
    }
}
