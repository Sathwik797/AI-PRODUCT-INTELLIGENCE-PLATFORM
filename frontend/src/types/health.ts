export interface LivenessResponse {
  status: string;
}

export interface HealthResponse {
  status: string;
  app_name: string;
  app_version: string;
}

export interface ReadinessResponse {
  status: 'ready' | 'not_ready';
  dependencies: {
    mysql: 'healthy' | 'unhealthy';
    faiss: 'healthy' | 'reconciling' | 'degraded' | 'critical' | 'uninitialized';
  };
  capabilities: {
    structured_search: boolean;
    semantic_search: boolean;
  };
}
