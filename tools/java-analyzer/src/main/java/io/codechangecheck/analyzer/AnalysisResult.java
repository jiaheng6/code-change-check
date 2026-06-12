package io.codechangecheck.analyzer;

import java.util.List;
import java.util.Map;

public record AnalysisResult(
    String status,
    String message,
    Map<String, Object> coverage,
    List<Evidence> evidence,
    List<String> errors
) {}
