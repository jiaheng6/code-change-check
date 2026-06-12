import java.util.Map;

class SafetyService {
    void build(Map<String, Object> result, Statistics statistics) {
        result.put("fireEvent.count.value", statistics.getFireSafetyIncidents());
    }
}

class Statistics {
    int getTotalFireAlarms() { return 0; }
    int getFireSafetyIncidents() { return 0; }
}
