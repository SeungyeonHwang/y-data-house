// Y-Data-House 고급 설정 타입 정의
// Python schemas.py와 동기화된 TypeScript 타입들

export enum QueryType {
  SIMPLE = "simple",
  COMPLEX = "complex", 
  FACTUAL = "factual",
  ANALYTICAL = "analytical"
}

export enum AnswerStyle {
  BULLET_POINTS = "bullet_points",
  STRUCTURED = "structured", 
  CONVERSATIONAL = "conversational",
  ANALYTICAL = "analytical"
}

export interface SearchConfig {
  max_results: number;                // 기본값: 15
  similarity_threshold: number;       // 기본값: 0.15
  precision_threshold: number;        // 기본값: 0.30
  enable_hyde: boolean;              // 기본값: true
  enable_rewrite: boolean;           // 기본값: true
  enable_rerank: boolean;            // 기본값: true
  enable_rag_fusion: boolean;        // 기본값: true
  rag_fusion_queries: number;        // 기본값: 4
  rerank_threshold: number;          // 기본값: 0.2
  rerank_top_k: number;              // 기본값: 6
}

export interface AnswerConfig {
  style: AnswerStyle;                // 기본값: BULLET_POINTS
  max_bullets: number;               // 기본값: 5
  include_sources: boolean;          // 기본값: true
  enable_self_refine: boolean;       // 기본값: true
  enable_react: boolean;             // 기본값: false
  max_tokens: number;                // 기본값: 800
  temperature: number;               // 기본값: 0.7
  enable_adaptive_temperature: boolean; // 기본값: true
  factual_temperature: number;       // 기본값: 0.4
  analytical_temperature: number;    // 기본값: 0.65
}

export interface RAGSettings {
  // 기본 설정
  fast_mode: boolean;                // 기본값: false
  debug_mode: boolean;               // 기본값: false
  enable_cache: boolean;             // 기본값: true
  
  // 검색 설정
  search_config: SearchConfig;
  
  // 답변 설정  
  answer_config: AnswerConfig;
  
  // UI 설정
  ui_preferences: {
    show_advanced_settings: boolean; // 기본값: false
    show_debug_info: boolean;        // 기본값: false
    auto_expand_sources: boolean;    // 기본값: false
    theme: "light" | "dark" | "auto"; // 기본값: "auto"
  };
  
  // 성능 설정
  performance: {
    target_response_time_ms: number;  // 기본값: 500
    max_concurrent_searches: number;  // 기본값: 1
    cache_ttl_hours: number;         // 기본값: 168 (7일)
  };
}

// 기본 설정값들
export const DEFAULT_SEARCH_CONFIG: SearchConfig = {
  max_results: 15,
  similarity_threshold: 0.15,
  precision_threshold: 0.30,
  enable_hyde: true,
  enable_rewrite: true,
  enable_rerank: true,
  enable_rag_fusion: true,
  rag_fusion_queries: 4,
  rerank_threshold: 0.2,
  rerank_top_k: 6
};

export const DEFAULT_ANSWER_CONFIG: AnswerConfig = {
  style: AnswerStyle.BULLET_POINTS,
  max_bullets: 5,
  include_sources: true,
  enable_self_refine: true,
  enable_react: false,
  max_tokens: 800,
  temperature: 0.7,
  enable_adaptive_temperature: true,
  factual_temperature: 0.4,
  analytical_temperature: 0.65
};

export const DEFAULT_RAG_SETTINGS: RAGSettings = {
  fast_mode: false,
  debug_mode: false,
  enable_cache: true,
  search_config: DEFAULT_SEARCH_CONFIG,
  answer_config: DEFAULT_ANSWER_CONFIG,
  ui_preferences: {
    show_advanced_settings: false,
    show_debug_info: false,
    auto_expand_sources: false,
    theme: "auto"
  },
  performance: {
    target_response_time_ms: 500,
    max_concurrent_searches: 1,
    cache_ttl_hours: 168
  }
};

// 설정 검증 함수들
export function validateSearchConfig(config: Partial<SearchConfig>): SearchConfig {
  return {
    max_results: Math.max(1, Math.min(config.max_results || 15, 50)),
    similarity_threshold: Math.max(0.0, Math.min(config.similarity_threshold || 0.15, 1.0)),
    precision_threshold: Math.max(0.0, Math.min(config.precision_threshold || 0.30, 1.0)),
    enable_hyde: config.enable_hyde ?? true,
    enable_rewrite: config.enable_rewrite ?? true,
    enable_rerank: config.enable_rerank ?? true,
    enable_rag_fusion: config.enable_rag_fusion ?? true,
    rag_fusion_queries: Math.max(2, Math.min(config.rag_fusion_queries || 4, 8)),
    rerank_threshold: Math.max(0.0, Math.min(config.rerank_threshold || 0.2, 1.0)),
    rerank_top_k: Math.max(1, Math.min(config.rerank_top_k || 6, 20))
  };
}

export function validateAnswerConfig(config: Partial<AnswerConfig>): AnswerConfig {
  return {
    style: config.style || AnswerStyle.BULLET_POINTS,
    max_bullets: Math.max(1, Math.min(config.max_bullets || 5, 10)),
    include_sources: config.include_sources ?? true,
    enable_self_refine: config.enable_self_refine ?? true,
    enable_react: config.enable_react ?? false,
    max_tokens: Math.max(100, Math.min(config.max_tokens || 800, 2000)),
    temperature: Math.max(0.0, Math.min(config.temperature || 0.7, 2.0)),
    enable_adaptive_temperature: config.enable_adaptive_temperature ?? true,
    factual_temperature: Math.max(0.0, Math.min(config.factual_temperature || 0.4, 1.0)),
    analytical_temperature: Math.max(0.0, Math.min(config.analytical_temperature || 0.65, 1.0))
  };
}

// 설정 프리셋들
export const SETTINGS_PRESETS = {
  default: DEFAULT_RAG_SETTINGS,
  
  fast: {
    ...DEFAULT_RAG_SETTINGS,
    fast_mode: true,
    search_config: {
      ...DEFAULT_SEARCH_CONFIG,
      enable_rerank: false,
      enable_rag_fusion: false,
      max_results: 8
    },
    answer_config: {
      ...DEFAULT_ANSWER_CONFIG,
      enable_self_refine: false,
      max_tokens: 600
    }
  } as RAGSettings,
  
  quality: {
    ...DEFAULT_RAG_SETTINGS,
    search_config: {
      ...DEFAULT_SEARCH_CONFIG,
      enable_rerank: true,
      enable_rag_fusion: true,
      max_results: 20,
      rerank_top_k: 8
    },
    answer_config: {
      ...DEFAULT_ANSWER_CONFIG,
      enable_self_refine: true,
      enable_react: true,
      max_tokens: 1200
    }
  } as RAGSettings,
  
  research: {
    ...DEFAULT_RAG_SETTINGS,
    debug_mode: true,
    search_config: {
      ...DEFAULT_SEARCH_CONFIG,
      similarity_threshold: 0.05,
      max_results: 25,
      enable_rag_fusion: true,
      rag_fusion_queries: 6
    },
    answer_config: {
      ...DEFAULT_ANSWER_CONFIG,
      style: AnswerStyle.ANALYTICAL,
      enable_react: true,
      max_tokens: 1500
    },
    ui_preferences: {
      show_advanced_settings: true,
      show_debug_info: true,
      auto_expand_sources: true,
      theme: "auto" as const
    }
  } as RAGSettings
};