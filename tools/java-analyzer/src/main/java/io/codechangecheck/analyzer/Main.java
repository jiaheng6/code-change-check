package io.codechangecheck.analyzer;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Path;

public final class Main {
    private Main() {}

    public static void main(String[] args) throws Exception {
        if (args.length == 0 || has(args, "--help")) {
            System.out.println("用法：java -jar java-analyzer.jar --project <目录>");
            return;
        }
        String project = value(args, "--project");
        if (project.isBlank()) {
            System.err.println("缺少 --project 参数。");
            System.exit(2);
        }
        AnalysisResult result = new SpoonAnalyzer().analyze(Path.of(project));
        System.out.println(new ObjectMapper().writeValueAsString(result));
        if (result.status().equals("blocked")) {
            System.exit(3);
        }
    }

    private static boolean has(String[] args, String expected) {
        for (String arg : args) {
            if (arg.equals(expected)) return true;
        }
        return false;
    }

    private static String value(String[] args, String name) {
        for (int index = 0; index + 1 < args.length; index++) {
            if (args[index].equals(name)) return args[index + 1];
        }
        return "";
    }
}
