package io.codechangecheck.analyzer;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import spoon.Launcher;
import spoon.reflect.CtModel;
import spoon.reflect.code.CtAssignment;
import spoon.reflect.code.CtIf;
import spoon.reflect.code.CtInvocation;
import spoon.reflect.code.CtLiteral;
import spoon.reflect.code.CtReturn;
import spoon.reflect.declaration.CtElement;
import spoon.reflect.declaration.CtField;
import spoon.reflect.declaration.CtMethod;
import spoon.reflect.declaration.CtType;
import spoon.reflect.visitor.filter.TypeFilter;

public final class SpoonAnalyzer {
    private static final Pattern ADDRESS = Pattern.compile("(?i)(internal|public|external).*(base)?url|https?://");
    private static final Pattern GUARD = Pattern.compile("(?i)(auth|permission|role|tenant|scope|token|login)");
    private static final Pattern STATE = Pattern.compile("(?i)(status|state|phase|workflow|approve|reject|cancel)");

    public AnalysisResult analyze(Path project) {
        List<Path> files = javaFiles(project);
        List<Evidence> evidence = new ArrayList<>();
        List<String> errors = new ArrayList<>();
        int parsed = 0;
        for (Path file : files) {
            try {
                Launcher launcher = new Launcher();
                launcher.addInputResource(file.toString());
                launcher.getEnvironment().setNoClasspath(true);
                launcher.getEnvironment().setIgnoreSyntaxErrors(true);
                launcher.getEnvironment().setComplianceLevel(17);
                launcher.getEnvironment().setCommentEnabled(false);
                launcher.buildModel();
                evidence.addAll(extract(project, launcher.getModel()));
                parsed++;
            } catch (RuntimeException error) {
                errors.add(relative(project, file) + "：" + error.getMessage());
            }
        }
        evidence.sort(Comparator.comparing(Evidence::file).thenComparingInt(Evidence::line).thenComparing(Evidence::kind));
        String status = parsed == 0 && !files.isEmpty() ? "blocked" : errors.isEmpty() ? "success" : "partial";
        Map<String, Object> coverage = new LinkedHashMap<>();
        coverage.put("java_files_total", files.size());
        coverage.put("java_files_parsed", parsed);
        coverage.put("java_files_failed", files.size() - parsed);
        coverage.put("core_complete", parsed == files.size());
        return new AnalysisResult(
            status,
            status.equals("success") ? "Java 语义分析完成。" : status.equals("partial") ? "部分 Java 文件未能解析。" : "Java 语义分析未能解析任何文件。",
            coverage,
            evidence,
            errors
        );
    }

    private List<Path> javaFiles(Path project) {
        try (Stream<Path> paths = Files.walk(project)) {
            return paths.filter(Files::isRegularFile)
                .filter(path -> path.toString().endsWith(".java"))
                .filter(path -> Stream.of(project.relativize(path).toString().split("[/\\\\]+"))
                    .noneMatch(part -> part.equals("target") || part.equals("build") || part.equals(".git") || part.equals(".svn")))
                .sorted()
                .toList();
        } catch (Exception error) {
            return List.of();
        }
    }

    private List<Evidence> extract(Path project, CtModel model) {
        List<Evidence> result = new ArrayList<>();
        for (CtType<?> type : model.getAllTypes()) {
            result.add(item(project, type, "symbol", type.getQualifiedName(), "", "", "", List.of(), "", type.getSimpleName()));
        }
        for (CtMethod<?> method : model.getElements(new TypeFilter<>(CtMethod.class))) {
            result.add(item(project, method, "symbol", methodSignature(method), "", "", "", List.of(), "", method.getSimpleName()));
            String annotations = method.getAnnotations().toString();
            if (annotations.contains("Mapping")) {
                result.add(item(project, method, "route", methodSignature(method), "route", annotations, "", List.of(), "", annotations));
            }
            if (GUARD.matcher(annotations).find()) {
                result.add(item(project, method, "guard", methodSignature(method), "annotation", annotations, "", List.of(), "permission", annotations));
            }
        }
        for (CtField<?> field : model.getElements(new TypeFilter<>(CtField.class))) {
            String annotations = field.getAnnotations().toString();
            if (annotations.contains("@Value") || annotations.contains("ConfigurationProperties")) {
                result.add(item(project, field, "config-read", ownerSymbol(field), field.getSimpleName(), annotations, "", List.of(), annotations, field.toString()));
            }
        }
        for (CtInvocation<?> invocation : model.getElements(new TypeFilter<>(CtInvocation.class))) {
            String executable = invocation.getExecutable() == null ? "" : invocation.getExecutable().getSimpleName();
            List<String> arguments = invocation.getArguments().stream().map(Object::toString).toList();
            String receiver = invocation.getTarget() == null ? "" : invocation.getTarget().toString();
            result.add(item(project, invocation, "call", ownerSymbol(invocation), executable, invocation.toString(), receiver, arguments, "", invocation.toString()));
            if (executable.equals("put") && invocation.getArguments().size() >= 2 && invocation.getArguments().get(0) instanceof CtLiteral<?> literal && literal.getValue() instanceof String slot) {
                result.add(item(project, invocation, "field-mapping", ownerSymbol(invocation), slot, invocation.getArguments().get(1).toString(), receiver, arguments, "", invocation.toString()));
            }
            if (executable.startsWith("set") && invocation.getArguments().size() == 1) {
                result.add(item(project, invocation, "field-mapping", ownerSymbol(invocation), executable.substring(3), invocation.getArguments().get(0).toString(), receiver, arguments, "", invocation.toString()));
            }
            if (ADDRESS.matcher(invocation.toString()).find()) {
                result.add(item(project, invocation, "http-argument", ownerSymbol(invocation), executable, invocation.toString(), receiver, arguments, addressValue(invocation.toString()), invocation.toString()));
            }
            if (Pattern.compile("(?i)(save|insert|update|delete|remove)").matcher(executable).find()) {
                result.add(item(project, invocation, "database-write", ownerSymbol(invocation), executable, invocation.toString(), receiver, arguments, "", invocation.toString()));
            }
        }
        for (CtAssignment<?, ?> assignment : model.getElements(new TypeFilter<>(CtAssignment.class))) {
            result.add(item(project, assignment, "assignment-flow", ownerSymbol(assignment), assignment.getAssigned().toString(), assignment.getAssignment().toString(), "", List.of(), "", assignment.toString()));
        }
        for (CtReturn<?> returned : model.getElements(new TypeFilter<>(CtReturn.class))) {
            String expression = returned.getReturnedExpression() == null ? "" : returned.getReturnedExpression().toString();
            result.add(item(project, returned, "return-flow", ownerSymbol(returned), "return", expression, "", List.of(), "", returned.toString()));
        }
        for (CtIf conditional : model.getElements(new TypeFilter<>(CtIf.class))) {
            String condition = conditional.getCondition().toString();
            if (GUARD.matcher(condition).find()) {
                result.add(item(project, conditional, "guard", ownerSymbol(conditional), "if", condition, "", List.of(), "permission", condition));
            }
            if (STATE.matcher(condition).find()) {
                result.add(item(project, conditional, "state-condition", ownerSymbol(conditional), "if", condition, "", List.of(), "state", condition));
            }
        }
        return result;
    }

    private Evidence item(Path project, CtElement element, String kind, String symbol, String slot, String source, String receiver, List<String> arguments, String value, String text) {
        String file = "";
        int line = 1;
        if (element.getPosition() != null && element.getPosition().isValidPosition()) {
            file = relative(project, element.getPosition().getFile().toPath());
            line = element.getPosition().getLine();
        }
        String id = file + "|" + symbol + "|" + kind + "|" + slot;
        return new Evidence(id, kind, file, line, symbol, slot, source, receiver, arguments, value, text);
    }

    private String ownerSymbol(CtElement element) {
        CtMethod<?> method = element.getParent(CtMethod.class);
        return method == null ? "" : methodSignature(method);
    }

    private String methodSignature(CtMethod<?> method) {
        CtType<?> type = method.getParent(CtType.class);
        String owner = type == null ? "" : type.getSimpleName();
        return owner + "#" + method.getSignature();
    }

    private String addressValue(String text) {
        String lower = text.toLowerCase();
        if (lower.contains("internal")) return "internal";
        if (lower.contains("public") || lower.contains("external") || lower.contains("http")) return "external";
        return "unknown";
    }

    private String relative(Path project, Path file) {
        try {
            return project.toAbsolutePath().normalize().relativize(file.toAbsolutePath().normalize()).toString().replace('\\', '/');
        } catch (IllegalArgumentException error) {
            return file.toString().replace('\\', '/');
        }
    }
}
