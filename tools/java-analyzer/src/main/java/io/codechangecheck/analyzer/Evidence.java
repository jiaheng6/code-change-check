package io.codechangecheck.analyzer;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

public record Evidence(
    String id,
    String kind,
    String file,
    int line,
    String symbol,
    String slot,
    @JsonProperty("source_expression") String sourceExpression,
    String receiver,
    List<String> arguments,
    String value,
    String text
) {}
