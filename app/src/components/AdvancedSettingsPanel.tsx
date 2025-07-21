import React, { useState, useEffect } from 'react';
import { invoke } from '@tauri-apps/api/core';
import {
  RAGSettings,
  SearchConfig,
  AnswerConfig,
  AnswerStyle,
  DEFAULT_RAG_SETTINGS,
  SETTINGS_PRESETS,
  validateSearchConfig,
  validateAnswerConfig
} from '../types/settings';

interface AdvancedSettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSettingsChange: (settings: RAGSettings) => void;
}

export const AdvancedSettingsPanel: React.FC<AdvancedSettingsPanelProps> = ({
  isOpen,
  onClose,
  onSettingsChange
}) => {
  const [settings, setSettings] = useState<RAGSettings>(DEFAULT_RAG_SETTINGS);
  const [loading, setLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<string>('');
  const [activeTab, setActiveTab] = useState<'basic' | 'search' | 'answer' | 'ui' | 'performance'>('basic');

  // 설정 로드
  useEffect(() => {
    if (isOpen) {
      loadSettings();
    }
  }, [isOpen]);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const loadedSettings = await invoke<RAGSettings>('load_rag_settings');
      setSettings(loadedSettings);
    } catch (error) {
      console.error('설정 로드 실패:', error);
      setSettings(DEFAULT_RAG_SETTINGS);
    } finally {
      setLoading(false);
    }
  };

  const saveSettings = async () => {
    setLoading(true);
    setSaveStatus('');
    try {
      // 설정 검증
      const validatedSettings = await invoke<RAGSettings>('validate_rag_settings', { settings });
      
      // 저장
      await invoke<string>('save_rag_settings', { settings: validatedSettings });
      
      setSettings(validatedSettings);
      onSettingsChange(validatedSettings);
      setSaveStatus('✅ 설정이 저장되었습니다');
      
      setTimeout(() => setSaveStatus(''), 3000);
    } catch (error) {
      console.error('설정 저장 실패:', error);
      setSaveStatus(`❌ 저장 실패: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const applyPreset = async (presetName: string) => {
    setLoading(true);
    try {
      const presetSettings = await invoke<RAGSettings>('apply_rag_preset', { presetName });
      setSettings(presetSettings);
      onSettingsChange(presetSettings);
      setSaveStatus(`✅ ${presetName} 프리셋이 적용되었습니다`);
      setTimeout(() => setSaveStatus(''), 3000);
    } catch (error) {
      console.error('프리셋 적용 실패:', error);
      setSaveStatus(`❌ 프리셋 적용 실패: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const resetSettings = async () => {
    if (confirm('모든 설정을 기본값으로 초기화하시겠습니까?')) {
      setLoading(true);
      try {
        await invoke<string>('reset_rag_settings');
        await loadSettings();
        setSaveStatus('✅ 설정이 초기화되었습니다');
        setTimeout(() => setSaveStatus(''), 3000);
      } catch (error) {
        console.error('설정 초기화 실패:', error);
        setSaveStatus(`❌ 초기화 실패: ${error}`);
      } finally {
        setLoading(false);
      }
    }
  };

  const updateSearchConfig = (updates: Partial<SearchConfig>) => {
    const newSearchConfig = { ...settings.search_config, ...updates };
    const validatedConfig = validateSearchConfig(newSearchConfig);
    setSettings({
      ...settings,
      search_config: validatedConfig
    });
  };

  const updateAnswerConfig = (updates: Partial<AnswerConfig>) => {
    const newAnswerConfig = { ...settings.answer_config, ...updates };
    const validatedConfig = validateAnswerConfig(newAnswerConfig);
    setSettings({
      ...settings,
      answer_config: validatedConfig
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* 헤더 */}
        <div className="bg-blue-600 text-white p-4 flex justify-between items-center">
          <h2 className="text-xl font-bold">🔧 고급 RAG 설정</h2>
          <button
            onClick={onClose}
            className="text-white hover:text-gray-200 text-2xl"
            disabled={loading}
          >
            ×
          </button>
        </div>

        {/* 프리셋 빠른 적용 */}
        <div className="p-4 bg-gray-50 border-b">
          <div className="flex gap-2 mb-2">
            <span className="font-semibold">빠른 프리셋:</span>
            <button
              onClick={() => applyPreset('default')}
              className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded text-sm"
              disabled={loading}
            >
              기본값
            </button>
            <button
              onClick={() => applyPreset('fast')}
              className="px-3 py-1 bg-green-200 hover:bg-green-300 rounded text-sm"
              disabled={loading}
            >
              ⚡ 빠름
            </button>
            <button
              onClick={() => applyPreset('quality')}
              className="px-3 py-1 bg-blue-200 hover:bg-blue-300 rounded text-sm"
              disabled={loading}
            >
              🎯 품질
            </button>
            <button
              onClick={() => applyPreset('research')}
              className="px-3 py-1 bg-purple-200 hover:bg-purple-300 rounded text-sm"
              disabled={loading}
            >
              🔬 연구
            </button>
          </div>
          {saveStatus && (
            <div className={`text-sm ${saveStatus.includes('❌') ? 'text-red-600' : 'text-green-600'}`}>
              {saveStatus}
            </div>
          )}
        </div>

        {/* 탭 네비게이션 */}
        <div className="flex bg-gray-100 border-b">
          {[
            { key: 'basic', label: '🚀 기본', icon: '🚀' },
            { key: 'search', label: '🔍 검색', icon: '🔍' },
            { key: 'answer', label: '💬 답변', icon: '💬' },
            { key: 'ui', label: '🎨 UI', icon: '🎨' },
            { key: 'performance', label: '⚡ 성능', icon: '⚡' }
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              className={`px-4 py-2 ${
                activeTab === tab.key
                  ? 'bg-white border-b-2 border-blue-500 text-blue-600'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* 설정 내용 */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading && (
            <div className="text-center py-4">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <p className="mt-2 text-gray-600">설정 처리 중...</p>
            </div>
          )}

          {!loading && (
            <>
              {/* 기본 설정 탭 */}
              {activeTab === 'basic' && (
                <div className="space-y-6">
                  <div>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.fast_mode}
                        onChange={(e) => setSettings({ ...settings, fast_mode: e.target.checked })}
                      />
                      <span className="font-semibold">⚡ 빠른 모드</span>
                    </label>
                    <p className="text-sm text-gray-600 mt-1">
                      성능 우선 모드. Re-ranking과 Self-Refine 비활성화로 응답 속도 향상
                    </p>
                  </div>

                  <div>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.debug_mode}
                        onChange={(e) => setSettings({ ...settings, debug_mode: e.target.checked })}
                      />
                      <span className="font-semibold">🔬 디버그 모드</span>
                    </label>
                    <p className="text-sm text-gray-600 mt-1">
                      검색 과정과 AI 처리 단계의 상세 정보 표시
                    </p>
                  </div>

                  <div>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.enable_cache}
                        onChange={(e) => setSettings({ ...settings, enable_cache: e.target.checked })}
                      />
                      <span className="font-semibold">💾 캐시 시스템</span>
                    </label>
                    <p className="text-sm text-gray-600 mt-1">
                      의미론적 캐시로 LLM 호출 40% 절감. 응답 속도 향상
                    </p>
                  </div>
                </div>
              )}

              {/* 검색 설정 탭 */}
              {activeTab === 'search' && (
                <div className="space-y-6">
                  <div>
                    <label className="block font-semibold mb-2">
                      🔍 최대 검색 결과 수: {settings.search_config.max_results}
                    </label>
                    <input
                      type="range"
                      min="5"
                      max="50"
                      value={settings.search_config.max_results}
                      onChange={(e) => updateSearchConfig({ max_results: Number(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-sm text-gray-600 mt-1">
                      검색할 문서 수. 많을수록 포괄적이지만 처리 시간 증가
                    </p>
                  </div>

                  <div>
                    <label className="block font-semibold mb-2">
                      📊 유사도 임계값: {settings.search_config.similarity_threshold.toFixed(2)}
                    </label>
                    <input
                      type="range"
                      min="0.05"
                      max="0.50"
                      step="0.05"
                      value={settings.search_config.similarity_threshold}
                      onChange={(e) => updateSearchConfig({ similarity_threshold: Number(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-sm text-gray-600 mt-1">
                      낮을수록 더 많은 문서 포함. 높을수록 정확한 문서만 선별
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.search_config.enable_hyde}
                        onChange={(e) => updateSearchConfig({ enable_hyde: e.target.checked })}
                      />
                      <span>🎯 HyDE</span>
                    </label>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.search_config.enable_rewrite}
                        onChange={(e) => updateSearchConfig({ enable_rewrite: e.target.checked })}
                      />
                      <span>✏️ 쿼리 재작성</span>
                    </label>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.search_config.enable_rerank}
                        onChange={(e) => updateSearchConfig({ enable_rerank: e.target.checked })}
                      />
                      <span>🔄 Re-ranking</span>
                    </label>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.search_config.enable_rag_fusion}
                        onChange={(e) => updateSearchConfig({ enable_rag_fusion: e.target.checked })}
                      />
                      <span>🎭 RAG-Fusion</span>
                    </label>
                  </div>

                  {settings.search_config.enable_rag_fusion && (
                    <div>
                      <label className="block font-semibold mb-2">
                        🎭 Fusion 쿼리 수: {settings.search_config.rag_fusion_queries}
                      </label>
                      <input
                        type="range"
                        min="2"
                        max="8"
                        value={settings.search_config.rag_fusion_queries}
                        onChange={(e) => updateSearchConfig({ rag_fusion_queries: Number(e.target.value) })}
                        className="w-full"
                      />
                      <p className="text-sm text-gray-600 mt-1">
                        다중 쿼리 생성 수. 많을수록 포괄적이지만 처리 시간 증가
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* 답변 설정 탭 */}
              {activeTab === 'answer' && (
                <div className="space-y-6">
                  <div>
                    <label className="block font-semibold mb-2">💬 답변 스타일</label>
                    <select
                      value={settings.answer_config.style}
                      onChange={(e) => updateAnswerConfig({ style: e.target.value as AnswerStyle })}
                      className="w-full p-2 border rounded"
                    >
                      <option value={AnswerStyle.BULLET_POINTS}>🔸 불릿 포인트</option>
                      <option value={AnswerStyle.STRUCTURED}>📋 구조화된 답변</option>
                      <option value={AnswerStyle.CONVERSATIONAL}>💭 대화형</option>
                      <option value={AnswerStyle.ANALYTICAL}>🔬 분석형</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold mb-2">
                      📝 최대 토큰 수: {settings.answer_config.max_tokens}
                    </label>
                    <input
                      type="range"
                      min="200"
                      max="2000"
                      step="100"
                      value={settings.answer_config.max_tokens}
                      onChange={(e) => updateAnswerConfig({ max_tokens: Number(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-sm text-gray-600 mt-1">
                      답변 길이 제한. 많을수록 상세하지만 처리 시간 증가
                    </p>
                  </div>

                  <div>
                    <label className="block font-semibold mb-2">
                      🌡️ Temperature: {settings.answer_config.temperature.toFixed(1)}
                    </label>
                    <input
                      type="range"
                      min="0.1"
                      max="1.5"
                      step="0.1"
                      value={settings.answer_config.temperature}
                      onChange={(e) => updateAnswerConfig({ temperature: Number(e.target.value) })}
                      className="w-full"
                    />
                    <p className="text-sm text-gray-600 mt-1">
                      창의성 수준. 낮을수록 일관성, 높을수록 창의성
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.answer_config.enable_self_refine}
                        onChange={(e) => updateAnswerConfig({ enable_self_refine: e.target.checked })}
                      />
                      <span>✨ Self-Refine</span>
                    </label>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.answer_config.enable_react}
                        onChange={(e) => updateAnswerConfig({ enable_react: e.target.checked })}
                      />
                      <span>🤔 ReAct 패턴</span>
                    </label>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.answer_config.enable_adaptive_temperature}
                        onChange={(e) => updateAnswerConfig({ enable_adaptive_temperature: e.target.checked })}
                      />
                      <span>🎯 적응형 Temperature</span>
                    </label>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.answer_config.include_sources}
                        onChange={(e) => updateAnswerConfig({ include_sources: e.target.checked })}
                      />
                      <span>📚 출처 포함</span>
                    </label>
                  </div>

                  {settings.answer_config.enable_adaptive_temperature && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block font-semibold mb-2">
                          📊 사실형 Temperature: {settings.answer_config.factual_temperature.toFixed(1)}
                        </label>
                        <input
                          type="range"
                          min="0.1"
                          max="0.8"
                          step="0.1"
                          value={settings.answer_config.factual_temperature}
                          onChange={(e) => updateAnswerConfig({ factual_temperature: Number(e.target.value) })}
                          className="w-full"
                        />
                      </div>
                      <div>
                        <label className="block font-semibold mb-2">
                          🧠 분석형 Temperature: {settings.answer_config.analytical_temperature.toFixed(1)}
                        </label>
                        <input
                          type="range"
                          min="0.3"
                          max="1.0"
                          step="0.1"
                          value={settings.answer_config.analytical_temperature}
                          onChange={(e) => updateAnswerConfig({ analytical_temperature: Number(e.target.value) })}
                          className="w-full"
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* UI 설정 탭 */}
              {activeTab === 'ui' && (
                <div className="space-y-6">
                  <div>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.ui_preferences.show_debug_info}
                        onChange={(e) => setSettings({
                          ...settings,
                          ui_preferences: { ...settings.ui_preferences, show_debug_info: e.target.checked }
                        })}
                      />
                      <span className="font-semibold">🔍 디버그 정보 표시</span>
                    </label>
                    <p className="text-sm text-gray-600 mt-1">
                      검색 시간, 토큰 사용량, 캐시 히트율 등 상세 정보 표시
                    </p>
                  </div>

                  <div>
                    <label className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        checked={settings.ui_preferences.auto_expand_sources}
                        onChange={(e) => setSettings({
                          ...settings,
                          ui_preferences: { ...settings.ui_preferences, auto_expand_sources: e.target.checked }
                        })}
                      />
                      <span className="font-semibold">📖 소스 자동 확장</span>
                    </label>
                    <p className="text-sm text-gray-600 mt-1">
                      답변과 함께 관련 영상 정보 자동으로 표시
                    </p>
                  </div>

                  <div>
                    <label className="block font-semibold mb-2">🎨 테마</label>
                    <select
                      value={settings.ui_preferences.theme}
                      onChange={(e) => setSettings({
                        ...settings,
                        ui_preferences: { ...settings.ui_preferences, theme: e.target.value }
                      })}
                      className="w-full p-2 border rounded"
                    >
                      <option value="auto">🌓 자동</option>
                      <option value="light">☀️ 라이트</option>
                      <option value="dark">🌙 다크</option>
                    </select>
                  </div>
                </div>
              )}

              {/* 성능 설정 탭 */}
              {activeTab === 'performance' && (
                <div className="space-y-6">
                  <div>
                    <label className="block font-semibold mb-2">
                      ⏱️ 목표 응답 시간: {settings.performance.target_response_time_ms}ms
                    </label>
                    <input
                      type="range"
                      min="300"
                      max="2000"
                      step="100"
                      value={settings.performance.target_response_time_ms}
                      onChange={(e) => setSettings({
                        ...settings,
                        performance: { ...settings.performance, target_response_time_ms: Number(e.target.value) }
                      })}
                      className="w-full"
                    />
                    <p className="text-sm text-gray-600 mt-1">
                      응답 시간 목표. 초과 시 성능 최적화 모드 자동 활성화
                    </p>
                  </div>

                  <div>
                    <label className="block font-semibold mb-2">
                      🔄 최대 동시 검색: {settings.performance.max_concurrent_searches}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="3"
                      value={settings.performance.max_concurrent_searches}
                      onChange={(e) => setSettings({
                        ...settings,
                        performance: { ...settings.performance, max_concurrent_searches: Number(e.target.value) }
                      })}
                      className="w-full"
                    />
                    <p className="text-sm text-gray-600 mt-1">
                      동시에 처리할 수 있는 검색 요청 수
                    </p>
                  </div>

                  <div>
                    <label className="block font-semibold mb-2">
                      💾 캐시 유지 시간: {settings.performance.cache_ttl_hours}시간
                    </label>
                    <input
                      type="range"
                      min="24"
                      max="720"
                      step="24"
                      value={settings.performance.cache_ttl_hours}
                      onChange={(e) => setSettings({
                        ...settings,
                        performance: { ...settings.performance, cache_ttl_hours: Number(e.target.value) }
                      })}
                      className="w-full"
                    />
                    <p className="text-sm text-gray-600 mt-1">
                      캐시된 응답을 유지할 시간 ({Math.round(settings.performance.cache_ttl_hours / 24)}일)
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* 버튼 영역 */}
        <div className="border-t p-4 flex justify-between">
          <div className="flex gap-2">
            <button
              onClick={resetSettings}
              className="px-4 py-2 bg-red-100 text-red-700 hover:bg-red-200 rounded"
              disabled={loading}
            >
              🔄 초기화
            </button>
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded"
              disabled={loading}
            >
              취소
            </button>
            <button
              onClick={saveSettings}
              className="px-4 py-2 bg-blue-600 text-white hover:bg-blue-700 rounded"
              disabled={loading}
            >
              {loading ? '저장 중...' : '💾 저장'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};