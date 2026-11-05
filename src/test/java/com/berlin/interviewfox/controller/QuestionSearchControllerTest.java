package com.berlin.interviewfox.controller;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.berlin.interviewfox.common.ErrorCode;
import com.berlin.interviewfox.exception.GlobalExceptionHandler;
import com.berlin.interviewfox.model.entity.Question;
import com.berlin.interviewfox.model.vo.QuestionVO;
import com.berlin.interviewfox.service.QuestionSearchService;
import com.berlin.interviewfox.service.QuestionService;
import com.berlin.interviewfox.service.impl.QuestionServiceImpl;
import com.berlin.interviewfox.service.search.QuestionSearchIndex;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import java.util.Collections;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.same;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class QuestionSearchControllerTest {

    private static final String PATH = "/question/list/page/vo";

    private final QuestionService questionService = mock(QuestionService.class);
    private final QuestionServiceImpl queryBuilder = new QuestionServiceImpl();
    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.standaloneSetup(new QuestionSearchController(new QuestionSearchService(questionService, null)))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
    }

    @Test
    void searchesUsingExistingKeywordFiltersAndRequestedPagination() throws Exception {
        when(questionService.getQueryWrapper(any()))
                .thenAnswer(call -> queryBuilder.getQueryWrapper(call.getArgument(0)));
        when(questionService.<Page<Question>>page(any(), any())).thenAnswer(call -> {
            Page<Question> page = call.getArgument(0);
            QueryWrapper<Question> filters = call.getArgument(1);
            assertEquals(2, page.getCurrent());
            assertEquals(5, page.getSize());
            assertTrue(filters.getSqlSegment().contains("title LIKE"));
            assertTrue(filters.getSqlSegment().contains("OR content LIKE"));
            assertTrue(filters.getParamNameValuePairs().containsValue("%Redis%"));
            return page;
        });

        QuestionVO question = new QuestionVO();
        question.setTitle("Redis cache");
        Page<QuestionVO> response = new Page<>(2, 5, 6);
        response.setRecords(Collections.singletonList(question));
        when(questionService.getQuestionVOPage(any(), any())).thenReturn(response);

        mvc.perform(post(PATH).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"searchText\":\"Redis\",\"current\":2,\"pageSize\":5}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.current").value(2))
                .andExpect(jsonPath("$.data.size").value(5))
                .andExpect(jsonPath("$.data.records[0].title").value("Redis cache"));
    }

    @Test
    void returnsAnEmptyPageAndDefaultsNullSortOrderToAscending() throws Exception {
        when(questionService.getQueryWrapper(any()))
                .thenAnswer(call -> queryBuilder.getQueryWrapper(call.getArgument(0)));
        when(questionService.<Page<Question>>page(any(), any())).thenAnswer(call -> {
            QueryWrapper<Question> filters = call.getArgument(1);
            assertTrue(filters.getSqlSegment().contains("ORDER BY title ASC"));
            return call.getArgument(0);
        });
        when(questionService.getQuestionVOPage(any(), any()))
                .thenAnswer(call -> queryBuilder.getQuestionVOPage(call.getArgument(0), call.getArgument(1)));

        mvc.perform(post(PATH).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"searchText\":\"no match\",\"sortField\":\"title\",\"sortOrder\":null}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.current").value(1))
                .andExpect(jsonPath("$.data.size").value(10))
                .andExpect(jsonPath("$.data.total").value(0))
                .andExpect(jsonPath("$.data.records").isEmpty());
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "null", "{\"current\":0}", "{\"pageSize\":0}", "{\"pageSize\":-1}", "{\"pageSize\":21}"})
    void rejectsMissingBodyAndInvalidPaginationBeforeQuerying(String body) throws Exception {
        mvc.perform(post(PATH).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.code").value(ErrorCode.PARAMS_ERROR.getCode()));

        verifyNoInteractions(questionService);
    }

    @Test
    void selectsElasticsearchWithoutQueryingMySqlForQuestions() throws Exception {
        QuestionSearchIndex index = mock(QuestionSearchIndex.class);
        Page<Question> hits = new Page<>(1, 10, 0);
        when(index.search(any(), eq(1), eq(10))).thenReturn(hits);
        when(questionService.getQuestionVOPage(any(), any()))
                .thenAnswer(call -> queryBuilder.getQuestionVOPage(call.getArgument(0), call.getArgument(1)));
        MockMvc elasticsearchMvc = MockMvcBuilders.standaloneSetup(
                new QuestionSearchController(new QuestionSearchService(questionService, index))).build();

        elasticsearchMvc.perform(post(PATH).param("engine", "elasticsearch")
                        .contentType(MediaType.APPLICATION_JSON).content("{\"searchText\":\"Redis\"}"))
                .andExpect(jsonPath("$.code").value(0))
                .andExpect(jsonPath("$.data.total").value(0));

        verify(questionService).getQuestionVOPage(same(hits), any());
        verifyNoMoreInteractions(questionService);
    }

    @Test
    void reportsDisabledElasticsearchWithoutSilentlyUsingMySql() throws Exception {
        mvc.perform(post(PATH).param("engine", "elasticsearch").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(jsonPath("$.code").value(ErrorCode.OPERATION_ERROR.getCode()));

        verifyNoInteractions(questionService);
    }
}
