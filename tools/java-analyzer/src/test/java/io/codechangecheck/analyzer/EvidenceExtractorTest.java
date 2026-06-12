package io.codechangecheck.analyzer;

import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class EvidenceExtractorTest {
    @Test
    void extractsMapFieldMappingAndValueSource() throws Exception {
        Path root = Files.createTempDirectory("java-analyzer-test");
        Files.writeString(
            root.resolve("SafetyService.java"),
            """
            import java.util.Map;
            class SafetyService {
              void build(Map<String, Object> result, Stats statistics) {
                result.put("fireEvent.count.value", statistics.getFireSafetyIncidents());
              }
            }
            class Stats { int getFireSafetyIncidents() { return 0; } }
            """
        );

        AnalysisResult result = new SpoonAnalyzer().analyze(root);

        assertTrue(result.evidence().stream().anyMatch(item ->
            item.kind().equals("field-mapping")
                && item.slot().equals("fireEvent.count.value")
                && item.sourceExpression().equals("statistics.getFireSafetyIncidents()")
        ));
    }
}
