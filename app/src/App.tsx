import React, { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { convertFileSrc } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { resolve, join } from '@tauri-apps/api/path';
import Fuse from 'fuse.js';
import './App.css';

interface VideoInfo {
  video_path: string;
  captions_path: string;
  title: string;
  channel: string;
  upload_date?: string;
  duration?: string;
  duration_seconds?: number;
  view_count?: number;
  topic?: string[];
  video_id?: string;
  source_url?: string;
  excerpt?: string;
}

interface ChannelInfo {
  url: string;
  name: string;
  enabled: boolean;
}

interface AppStatus {
  total_videos: number;
  total_channels: number;
  vault_size_mb: number;
  last_download?: string;
  vector_db_status: string;
}

interface ChannelVideos {
  channel_name: string;
  videos: VideoInfo[];
}

interface RecentVideos {
  channels: ChannelVideos[];
}

interface DownloadProgress {
  channel: string;
  status: string;
  progress: number;
  current_video: string;
  total_videos: number;
  completed_videos: number;
  log_message: string;
}

interface CaptionLine {
  index: number;
  content: string;
  timestamp?: string;
  start_time?: number;
  end_time?: number;
}

type TabType = 'dashboard' | 'channels' | 'videos' | 'search' | 'ai' | 'settings';

// 절대경로로 변환하여 asset URL 생성
async function toAssetUrl(vaultRelPath: string): Promise<string> {
  try {
         // 프로젝트 루트에서 vault 경로로 절대경로 생성
    const projectRoot = await invoke<string>('get_project_root_path');
    const absolutePath = await resolve(projectRoot, vaultRelPath);
    return convertFileSrc(absolutePath);
  } catch (error) {
    console.error('Asset URL 생성 실패:', error);
    return '';
  }
}

// 마크다운에서 실제 자막 내용만 파싱하는 함수 (개선된 버전)
function parseCaptionsFromMarkdown(markdownText: string): CaptionLine[] {
  const lines = markdownText.split(/\r?\n/);
  const captions: CaptionLine[] = [];
  let inCaptionSection = false;
  let skipNextEmptyLine = false;
  let index = 0;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    
    // YAML frontmatter 건너뛰기
    if (line === '---') {
      if (i === 0) {
        // frontmatter 시작
        while (i < lines.length - 1) {
          i++;
          if (lines[i].trim() === '---') {
            break; // frontmatter 끝
          }
        }
        continue;
      }
    }
    
    // "## 📝 자막 내용" 섹션 찾기
    if (line.includes('📝 자막 내용') || line.includes('자막 내용') || line.includes('## 자막') || line.includes('## Transcript')) {
      inCaptionSection = true;
      skipNextEmptyLine = true;
      continue;
    }
    
    // 다른 섹션 헤더를 만나면 자막 섹션 종료
    if (inCaptionSection && line.startsWith('##') && !line.includes('자막')) {
      break;
    }
    
    // 자막 섹션 내에서 실제 내용 추출
    if (inCaptionSection) {
      if (skipNextEmptyLine && line === '') {
        skipNextEmptyLine = false;
        continue;
      }
      
      if (line !== '' && !line.startsWith('#') && !line.startsWith('---')) {
        // 시간 정보나 불필요한 정보 제거
        let cleanedLine = line;
        let timestamp = '';
        let startTime = 0;
        let endTime = 0;
        
        // 시간 스탬프 추출 및 제거 (예: [00:12:34] 형식)
        const timeMatch = cleanedLine.match(/\[(\d+:\d+:\d+)\]/);
        if (timeMatch) {
          timestamp = timeMatch[1];
          // 시간을 초로 변환
          const timeParts = timestamp.split(':').map(Number);
          startTime = timeParts[0] * 3600 + timeParts[1] * 60 + timeParts[2];
          cleanedLine = cleanedLine.replace(/\[\d+:\d+:\d+\]/g, '').trim();
        }
        
        // 화자 정보 제거 (예: "Speaker: " 형식)
        cleanedLine = cleanedLine.replace(/^[^:]+:\s*/, '').trim();
        // 불필요한 마크다운 포맷 제거
        cleanedLine = cleanedLine.replace(/^[*-]\s*/, '').trim();
        
        if (cleanedLine.length > 0) {
          captions.push({
            index: index++,
            content: cleanedLine,
            timestamp,
            start_time: startTime,
            end_time: startTime + 5 // 기본 5초 길이로 설정
          });
        }
      }
    }
  }
  
  // 자막 섹션을 찾지 못한 경우, 전체 내용에서 의미 있는 텍스트 추출
  if (captions.length === 0) {
    index = 0;
    for (const line of lines) {
      const cleanedLine = line.trim();
      if (cleanedLine.length > 0 && 
          !cleanedLine.startsWith('---') && 
          !cleanedLine.startsWith('#') && 
          !cleanedLine.includes('title:') && 
          !cleanedLine.includes('upload:') && 
          !cleanedLine.includes('channel:') && 
          !cleanedLine.includes('video_id:') && 
          !cleanedLine.includes('topic:') && 
          !cleanedLine.includes('source_url:')) {
        // 시간 정보 제거
        let processedLine = cleanedLine.replace(/\[\d+:\d+:\d+\]/g, '').trim();
        processedLine = processedLine.replace(/^[*-]\s*/, '').trim();
        
        if (processedLine.length > 10) { // 너무 짧은 텍스트 제외
          captions.push({
            index: index++,
            content: processedLine,
            timestamp: '',
            start_time: 0,
            end_time: 0
          });
        }
      }
    }
  }
  
  return captions;
}



export default function App() {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  const [appStatus, setAppStatus] = useState<AppStatus | null>(null);
  
  // 비디오 관련 상태
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [recentVideos, setRecentVideos] = useState<RecentVideos>({ channels: [] });
  const [selectedVideo, setSelectedVideo] = useState<VideoInfo | null>(null);
  const [captions, setCaptions] = useState<CaptionLine[]>([]);
  const [fuse, setFuse] = useState<Fuse<CaptionLine>>();
  
  // 자막 관련 새로운 상태들
  const [captionFilter, setCaptionFilter] = useState('');
  const [filteredCaptions, setFilteredCaptions] = useState<CaptionLine[]>([]);
  const [highlightedCaptions, setHighlightedCaptions] = useState<Set<number>>(new Set());
  const [captionLoading, setCaptionLoading] = useState(false);
  const [currentCaptionIndex, setCurrentCaptionIndex] = useState(-1);

  
  // Range 지원 비디오 서버 상태
  const [videoServerPort, setVideoServerPort] = useState<number | null>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [serverLoading, setServerLoading] = useState(false);
  
  // 채널 관련 상태
  const [channels, setChannels] = useState<ChannelInfo[]>([]);
  const [newChannelUrl, setNewChannelUrl] = useState('');
  
  // 검색 관련 상태
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<CaptionLine[]>([]);
  const [vectorSearchQuery, setVectorSearchQuery] = useState('');
  const [vectorSearchResults, setVectorSearchResults] = useState('');
  
  // 키워드 검색 관련 상태
  const [keywordSearchQuery, setKeywordSearchQuery] = useState('');
  const [keywordSearchResults, setKeywordSearchResults] = useState<VideoInfo[]>([]);
  const [filteredVideos, setFilteredVideos] = useState<VideoInfo[]>([]);
  const [sortOrder, setSortOrder] = useState<'date' | 'title' | 'views' | 'duration'>('date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  
  // AI 관련 상태
  const [aiQuestion, setAiQuestion] = useState('');
  const [aiAnswer, setAiAnswer] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  
  // 비디오 코덱 호환성 상태
  const [videoError, setVideoError] = useState<string | null>(null);
  const [codecInfo, setCodecInfo] = useState<string | null>(null);
  
  // 비디오 변환 상태
  const [conversionLoading, setConversionLoading] = useState(false);
  const [conversionProgress, setConversionProgress] = useState<DownloadProgress | null>(null);
  const [conversionLogs, setConversionLogs] = useState<string[]>([]);
  const [showConversionModal, setShowConversionModal] = useState(false);
  
  // 작업 상태
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState<DownloadProgress | null>(null);
  const [downloadLogs, setDownloadLogs] = useState<string[]>([]);
  const [showProgressModal, setShowProgressModal] = useState(false);
  const [videoQuality, setVideoQuality] = useState<string>('720p');
  
  // 벡터 임베딩 상태
  const [embedLoading, setEmbedLoading] = useState(false);
  const [embeddingProgress, setEmbeddingProgress] = useState<DownloadProgress | null>(null);
  const [embeddingLogs, setEmbeddingLogs] = useState<string[]>([]);
  const [showEmbeddingModal, setShowEmbeddingModal] = useState(false);
  const [availableChannels, setAvailableChannels] = useState<string[]>([]);
  const [selectedChannels, setSelectedChannels] = useState<string[]>([]);
  const [showChannelSelector, setShowChannelSelector] = useState(false);
  
  // 정합성 검사 상태
  const [checkLoading, setCheckLoading] = useState(false);
  const [integrityProgress, setIntegrityProgress] = useState<DownloadProgress | null>(null);
  const [integrityLogs, setIntegrityLogs] = useState<string[]>([]);
  const [showIntegrityModal, setShowIntegrityModal] = useState(false);
  
  // 로딩 및 에러 상태
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState('');
  
  // 채널별 토글 상태
  const [collapsedChannels, setCollapsedChannels] = useState<Set<string>>(new Set());

  // 비디오 서버 시작
  const startVideoServer = async () => {
    setServerLoading(true);
    try {
      const port = await invoke<number>('start_video_server');
      setVideoServerPort(port);
      
      // 현재 선택된 비디오가 있으면 URL 생성
      if (selectedVideo) {
        const url = await invoke<string>('get_video_url', { videoPath: selectedVideo.video_path });
        setVideoUrl(url);
      }
    } catch (error) {
      console.error('비디오 서버 시작 실패:', error);
      alert(`서버 시작 실패: ${error}`);
    } finally {
      setServerLoading(false);
    }
  };

  // 비디오 서버 중지
  const stopVideoServer = async () => {
    try {
      await invoke('stop_video_server');
      setVideoServerPort(null);
      setVideoUrl(null);
    } catch (error) {
      console.error('비디오 서버 중지 실패:', error);
    }
  };

  // 비디오 서버 상태 확인
  const checkVideoServerStatus = async () => {
    try {
      const port = await invoke<number | null>('get_video_server_status');
      setVideoServerPort(port);
    } catch (error) {
      console.error('서버 상태 확인 실패:', error);
    }
  };

  // 비디오 목록이 변경될 때 필터링된 목록 업데이트
  useEffect(() => {
    setFilteredVideos(videos);
  }, [videos]);

  // 자막 필터가 변경될 때 자동으로 필터링 적용
  useEffect(() => {
    if (captions.length > 0) {
      applyCaptionFilter();
    }
  }, [captionFilter, captions]);

  // 초기 데이터 로드
  useEffect(() => {
    loadAppData();
    loadDebugInfo();
    checkVideoServerStatus(); // 서버 상태 확인
    
    // 다운로드 진행 상황 이벤트 리스너
    const unlistenDownload = listen<DownloadProgress>('download-progress', (event) => {
      const progress = event.payload;
      setDownloadProgress(progress);
      
      // 빈 로그 메시지 필터링 및 중복 제거
      if (progress.log_message && progress.log_message.trim()) {
        setDownloadLogs(prev => {
          const newLogs = [...prev, progress.log_message];
          // 중복된 연속 로그 제거
          const filtered = newLogs.filter((log, index) => 
            index === 0 || log !== newLogs[index - 1]
          );
          return filtered.slice(-100); // 최근 100개 로그만 유지
        });
      }
    });
    
    // 벡터 임베딩 진행 상황 이벤트 리스너
    const unlistenEmbedding = listen<DownloadProgress>('embedding-progress', (event) => {
      const progress = event.payload;
      setEmbeddingProgress(progress);
      if (progress.log_message && progress.log_message.trim()) {
        setEmbeddingLogs(prev => {
          const newLogs = [...prev, progress.log_message];
          // 중복 로그 방지
          const filtered = newLogs.filter((log, index) => 
            index === 0 || log !== newLogs[index - 1]
          );
          return filtered.slice(-100); // 최근 100개 로그만 유지
        });
      }
    });
    
    // 정합성 검사 진행 상황 이벤트 리스너
    const unlistenIntegrity = listen<DownloadProgress>('integrity-progress', (event) => {
      const progress = event.payload;
      setIntegrityProgress(progress);
      setIntegrityLogs(prev => [...prev, progress.log_message].slice(-50));
    });
    
    // 비디오 변환 진행 상황 이벤트 리스너
    const unlistenConversion = listen<DownloadProgress>('conversion-progress', (event) => {
      const progress = event.payload;
      setConversionProgress(progress);
      if (progress.log_message && progress.log_message.trim()) {
        setConversionLogs(prev => {
          const newLogs = [...prev, progress.log_message];
          const filtered = newLogs.filter((log, index) => 
            index === 0 || log !== newLogs[index - 1]
          );
          return filtered.slice(-100);
        });
      }
      
      // 변환 완료 시 비디오 URL 새로고침 및 모달 자동 닫기
      if (progress.status === "완료" && progress.progress === 100.0) {
        setTimeout(async () => {
          try {
            if (selectedVideo && videoServerPort) {
              const url = await invoke<string>('get_video_url', { videoPath: selectedVideo.video_path });
              setVideoUrl(url + '?t=' + Date.now()); // 캐시 방지를 위한 timestamp 추가
              setVideoError(null); // 에러 초기화
              setCodecInfo('MP4 컨테이너 (H.264 코덱)'); // 변환 완료 후 코덱 정보 업데이트
              
              // 비디오 플레이어로 포커싱 및 스크롤
              setTimeout(() => {
                const videoElement = document.querySelector('.video-player') as HTMLVideoElement;
                if (videoElement) {
                  videoElement.scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'center' 
                  });
                  videoElement.focus();
                }
              }, 1000); // 비디오 로드 후 포커싱
            }
          } catch (error) {
            console.error('변환 후 비디오 URL 새로고침 실패:', error);
          }
          
          // 모달 바로 닫기
          setShowConversionModal(false);
          setConversionLoading(false);
        }, 500); // 0.5초 후 바로 처리
      }
    });
    
    return () => {
      unlistenDownload.then(f => f());
      unlistenEmbedding.then(f => f());
      unlistenIntegrity.then(f => f());
      unlistenConversion.then(f => f());
    };
  }, []);

  const loadAppData = async () => {
    try {
      setLoading(true);
      const [statusResult, videosResult, channelsResult, recentResult, availableChannelsResult] = await Promise.all([
        invoke<AppStatus>('get_app_status'),
        invoke<VideoInfo[]>('list_videos'),
        invoke<ChannelInfo[]>('list_channels'),
        invoke<RecentVideos>('get_recent_videos_by_channel', { limitPerChannel: 5 }),
        invoke<string[]>('get_available_channels_for_embedding')
      ]);
      
      setAppStatus(statusResult);
      setVideos(videosResult);
      setChannels(channelsResult);
      setRecentVideos(recentResult);
      setAvailableChannels(availableChannelsResult);
      setSelectedChannels(availableChannelsResult); // 기본적으로 모든 채널 선택
      setError(null);
    } catch (err) {
      setError(err as string);
    } finally {
      setLoading(false);
    }
  };

  const loadDebugInfo = async () => {
    try {
      const info = await invoke<string>('get_debug_info');
      setDebugInfo(info);
    } catch (error) {
      setDebugInfo(`디버그 정보 로드 실패: ${error}`);
    }
  };

  // 선택된 비디오의 캡션 로드 및 비디오 URL 생성
  useEffect(() => {
    if (!selectedVideo) {
      setCaptions([]);
      setFilteredCaptions([]);
      setFuse(undefined);
      setVideoUrl(null);
      setHighlightedCaptions(new Set());
      setCaptionFilter('');
      setCurrentCaptionIndex(-1);
      return;
    }

    // 선택된 비디오로 스크롤하여 포커싱
    if (activeTab === 'videos') {
      setTimeout(() => {
        const activeVideoElement = document.querySelector('.video-item.video-item-active');
        if (activeVideoElement) {
          activeVideoElement.scrollIntoView({
            behavior: 'smooth',
            block: 'center'
          });
        }
      }, 100); // 탭 전환 후 잠시 대기
    }
    
    // 캡션 파일 로드 및 파싱
    setCaptionLoading(true);
    toAssetUrl(selectedVideo.captions_path)
      .then((assetUrl) => fetch(assetUrl))
      .then((response) => response.text())
      .then((text) => {
        // 마크다운에서 실제 자막 내용만 추출
        const parsedCaptions = parseCaptionsFromMarkdown(text);
        setCaptions(parsedCaptions);
        setFilteredCaptions(parsedCaptions);
        setFuse(new Fuse(parsedCaptions, { keys: ['content'], threshold: 0.3 }));
      })
      .catch((error) => {
        console.error('❌ 캡션 파일 읽기 실패:', error);
        setCaptions([]);
        setFilteredCaptions([]);
        setFuse(undefined);
      })
      .finally(() => {
        setCaptionLoading(false);
      });

    // 비디오 URL 생성 (서버가 실행 중인 경우) 또는 서버 자동 시작
    const generateVideoUrl = async () => {
      if (videoServerPort) {
        // 서버가 이미 실행 중이면 URL 생성
        try {
          const url = await invoke<string>('get_video_url', { videoPath: selectedVideo.video_path });
          setVideoUrl(url);
          setVideoError(null);
          setCodecInfo('MP4 컨테이너 (H.264 또는 AV1 코덱)');
        } catch (error) {
          console.error('비디오 URL 생성 실패:', error);
          setVideoUrl(null);
          setVideoError('비디오 URL 생성에 실패했습니다.');
        }
      } else {
        // 서버가 중지되어 있으면 자동으로 시작
        setServerLoading(true);
        try {
          const port = await invoke<number>('start_video_server');
          setVideoServerPort(port);
          
          // 서버 시작 후 URL 생성
          const url = await invoke<string>('get_video_url', { videoPath: selectedVideo.video_path });
          setVideoUrl(url);
          setVideoError(null);
          setCodecInfo('MP4 컨테이너 (H.264 또는 AV1 코덱)');
        } catch (error) {
          console.error('서버 자동 시작 또는 URL 생성 실패:', error);
          setVideoUrl(null);
          setVideoError(`서버 시작 실패: ${error}`);
        } finally {
          setServerLoading(false);
        }
      }
    };

    generateVideoUrl();
  }, [selectedVideo, videoServerPort]);

  // 비디오 에러 처리
  const handleVideoError = (e: React.SyntheticEvent<HTMLVideoElement, Event>) => {
    console.error('Video load error:', e);
    const video = e.currentTarget;
    
    if (video.error) {
      let errorMessage = '비디오 재생 오류: ';
      switch (video.error.code) {
        case MediaError.MEDIA_ERR_ABORTED:
          errorMessage += '재생이 중단되었습니다.';
          break;
        case MediaError.MEDIA_ERR_NETWORK:
          errorMessage += '네트워크 오류가 발생했습니다.';
          break;
        case MediaError.MEDIA_ERR_DECODE:
          errorMessage += '비디오 디코딩 오류 (AV1 코덱 호환성 문제일 수 있습니다)';
          break;
        case MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED:
          errorMessage += '지원되지 않는 비디오 포맷 또는 코덱입니다';
          break;
        default:
          errorMessage += '알 수 없는 오류가 발생했습니다.';
      }
      setVideoError(errorMessage);
    }
  };

  // 시스템 플레이어로 열기
  const openInSystemPlayer = async () => {
    if (!selectedVideo) return;
    
    try {
      // macOS의 경우 'open' 명령어 사용
      await invoke('open_in_system_player', { 
        videoPath: selectedVideo.video_path 
      });
    } catch (error) {
      console.error('시스템 플레이어 실행 실패:', error);
      alert('시스템 플레이어로 열기에 실패했습니다. 파일을 직접 열어보세요.');
    }
  };

  // 비디오 변환 함수
  const convertVideo = async (quality: string = 'keep', codec: string = 'h264', backup: boolean = false) => {
    if (!selectedVideo) return;
    
    setConversionLoading(true);
    setConversionProgress(null);
    setConversionLogs([]);
    setShowConversionModal(true);
    
    try {
      const result = await invoke<string>('convert_video_file', {
        videoPath: selectedVideo.video_path,
        quality,
        codec,
        backup
      });
      console.log('변환 시작:', result);
    } catch (error) {
      console.error('비디오 변환 실패:', error);
      setConversionLogs(prev => [...prev, `❌ 변환 실패: ${error}`]);
    } finally {
      setConversionLoading(false);
    }
  };

  // 변환 중단
  const cancelConversion = async () => {
    try {
      await invoke('cancel_conversion');
      setConversionLogs(prev => [...prev, '🛑 사용자가 변환을 중단했습니다']);
    } catch (error) {
      setConversionLogs(prev => [...prev, `❌ 중단 실패: ${error}`]);
    }
  };

  // 캡션 검색
  const searchCaptions = () => {
    if (!fuse || searchQuery.length < 2) {
      setSearchResults([]);
      setHighlightedCaptions(new Set());
      return;
    }
    const results = fuse.search(searchQuery);
    const resultItems = results.map((result: any) => result.item);
    const highlightedIndices = new Set(resultItems.map((item: CaptionLine) => item.index));
    
    setSearchResults(resultItems);
    setHighlightedCaptions(highlightedIndices);
  };

  // 자막 필터 적용
  const applyCaptionFilter = () => {
    if (!captionFilter.trim()) {
      setFilteredCaptions(captions);
      setHighlightedCaptions(new Set());
      return;
    }
    
    const lowerQuery = captionFilter.toLowerCase();
    const filtered = captions.filter(caption => 
      caption.content.toLowerCase().includes(lowerQuery)
    );
    setFilteredCaptions(filtered);
    
    const highlightedIndices = new Set(filtered.map(caption => caption.index));
    setHighlightedCaptions(highlightedIndices);
  };

  // 자막 필터 초기화
  const clearCaptionFilter = () => {
    setCaptionFilter('');
    setFilteredCaptions(captions);
    setHighlightedCaptions(new Set());
  };

  // 자막 하이라이트 텍스트 생성
  const getHighlightedText = (text: string, query: string): string => {
    if (!query.trim()) return text;
    
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return text.replace(regex, '<span class="highlight">$1</span>');
  };

  // 자막 전체 복사 함수
  const copyAllCaptions = async () => {
    if (captions.length === 0) return;
    
    try {
      const captionsText = captions
        .map((caption, index) => {
          const timestamp = caption.timestamp ? `[${caption.timestamp}] ` : '';
          return `${index + 1}. ${timestamp}${caption.content}`;
        })
        .join('\n\n');
      
      await navigator.clipboard.writeText(captionsText);
    } catch (error) {
      console.error('복사 실패:', error);
    }
  };

  // 벡터 검색
  const performVectorSearch = async () => {
    if (!vectorSearchQuery.trim()) return;
    
    try {
      const result = await invoke<string>('vector_search', { query: vectorSearchQuery });
      setVectorSearchResults(result);
    } catch (err) {
      setVectorSearchResults(`에러: ${err}`);
    }
  };

  // 키워드 검색
  const performKeywordSearch = () => {
    if (!keywordSearchQuery.trim()) {
      setKeywordSearchResults([]);
      setFilteredVideos(videos);
      return;
    }
    
    const query = keywordSearchQuery.toLowerCase();
    const results = videos.filter(video => 
      video.title.toLowerCase().includes(query) ||
      video.channel.toLowerCase().includes(query) ||
      (video.topic && video.topic.some(tag => tag.toLowerCase().includes(query))) ||
      (video.excerpt && video.excerpt.toLowerCase().includes(query))
    );
    
    setKeywordSearchResults(results);
    setFilteredVideos(results);
  };

  // 정렬 함수
  const sortVideos = (videosToSort: VideoInfo[], order: typeof sortOrder, direction: typeof sortDirection) => {
    return [...videosToSort].sort((a, b) => {
      let aValue: any, bValue: any;
      
      switch (order) {
        case 'date':
          aValue = a.upload_date ? new Date(a.upload_date).getTime() : 0;
          bValue = b.upload_date ? new Date(b.upload_date).getTime() : 0;
          break;
        case 'title':
          aValue = a.title.toLowerCase();
          bValue = b.title.toLowerCase();
          break;
        case 'views':
          aValue = a.view_count || 0;
          bValue = b.view_count || 0;
          break;
        case 'duration':
          aValue = a.duration_seconds || 0;
          bValue = b.duration_seconds || 0;
          break;
        default:
          return 0;
      }
      
      if (direction === 'asc') {
        return aValue > bValue ? 1 : aValue < bValue ? -1 : 0;
      } else {
        return aValue < bValue ? 1 : aValue > bValue ? -1 : 0;
      }
    });
  };

  // 정렬 변경 핸들러
  const handleSortChange = (newOrder: typeof sortOrder) => {
    if (newOrder === sortOrder) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortOrder(newOrder);
      setSortDirection('desc');
    }
  };

  // 정렬된 비디오 목록 가져오기
  const getSortedVideos = () => {
    return sortVideos(filteredVideos, sortOrder, sortDirection);
  };

  // AI 질문
  const askAI = async () => {
    if (!aiQuestion.trim()) return;
    
    setAiLoading(true);
    try {
      const result = await invoke<string>('ask_rag', { query: aiQuestion });
      setAiAnswer(result);
    } catch (err) {
      setAiAnswer(`에러: ${err}`);
    } finally {
      setAiLoading(false);
    }
  };

  // 채널 추가
  const addChannel = async () => {
    if (!newChannelUrl.trim()) return;
    
    try {
      await invoke('add_channel', { url: newChannelUrl });
      setNewChannelUrl('');
      loadAppData();
    } catch (err) {
      alert(`채널 추가 실패: ${err}`);
    }
  };

  // 채널 삭제
  const removeChannel = async (url: string) => {
    try {
      await invoke('remove_channel', { url });
      loadAppData();
    } catch (err) {
      alert(`채널 삭제 실패: ${err}`);
    }
  };

  // 채널 토글
  const toggleChannel = async (url: string) => {
    try {
      await invoke('toggle_channel', { url });
      loadAppData();
    } catch (err) {
      alert(`채널 상태 변경 실패: ${err}`);
    }
  };

  // 비디오 다운로드 (진행 상황 포함)
  const downloadVideos = async () => {
    setDownloadLoading(true);
    setDownloadProgress(null);
    setDownloadLogs([]);
    setShowProgressModal(true);
    
    try {
      const result = await invoke<string>('download_videos_with_progress_and_quality', { quality: videoQuality });
      // 완료 후 데이터 새로고침
      await loadAppData();
    } catch (err) {
      setDownloadLogs(prev => [...prev, `❌ 다운로드 실패: ${err}`]);
    } finally {
      setDownloadLoading(false);
    }
  };

  // 채널 선택 토글
  const toggleChannelSelection = (channel: string) => {
    setSelectedChannels(prev => 
      prev.includes(channel) 
        ? prev.filter(c => c !== channel)
        : [...prev, channel]
    );
  };

  // 모든 채널 선택/해제
  const toggleAllChannels = () => {
    setSelectedChannels(prev => 
      prev.length === availableChannels.length ? [] : [...availableChannels]
    );
  };

  // 채널별 벡터 임베딩 생성
  const createEmbeddingsForChannels = async () => {
    if (selectedChannels.length === 0) {
      alert('생성할 채널을 선택해주세요.');
      return;
    }

    setEmbedLoading(true);
    setEmbeddingProgress(null);
    setEmbeddingLogs([]);
    setShowEmbeddingModal(true);
    setShowChannelSelector(false);
    
    try {
      const result = await invoke<string>('create_embeddings_for_channels_with_progress', { 
        channels: selectedChannels 
      });
      // 완료 후 데이터 새로고침
      await loadAppData();
    } catch (err) {
      setEmbeddingLogs(prev => [...prev, `❌ 임베딩 생성 실패: ${err}`]);
    } finally {
      setEmbedLoading(false);
    }
  };

  // 임베딩 중단
  const cancelEmbedding = async () => {
    try {
      await invoke('cancel_embedding');
      setEmbeddingLogs(prev => [...prev, '🛑 사용자가 임베딩 생성을 중단했습니다']);
    } catch (err) {
      setEmbeddingLogs(prev => [...prev, `❌ 중단 실패: ${err}`]);
    }
  };

  // 데이터 정합성 검사 (진행 상황 포함)
  const checkIntegrity = async () => {
    setCheckLoading(true);
    setIntegrityProgress(null);
    setIntegrityLogs([]);
    setShowIntegrityModal(true);
    
    try {
      const result = await invoke<string>('check_integrity_with_progress');
      // 완료 후 데이터 새로고침
      await loadAppData();
    } catch (err) {
      setIntegrityLogs(prev => [...prev, `❌ 정합성 검사 실패: ${err}`]);
    } finally {
      setCheckLoading(false);
    }
  };

  // 다운로드 중단
  const cancelDownload = async () => {
    try {
      await invoke('cancel_download');
      setDownloadLogs(prev => [...prev, '🛑 사용자가 다운로드를 중단했습니다']);
    } catch (err) {
      setDownloadLogs(prev => [...prev, `❌ 중단 실패: ${err}`]);
    }
  };
  
  // 채널 토글 함수
  const toggleChannelCollapse = (channelName: string) => {
    setCollapsedChannels(prev => {
      const newSet = new Set(prev);
      if (newSet.has(channelName)) {
        newSet.delete(channelName);
      } else {
        newSet.add(channelName);
      }
      return newSet;
    });
  };
  
  // 채널별로 비디오 그룹화
  const groupVideosByChannel = (videos: VideoInfo[]) => {
    const grouped = videos.reduce((acc, video) => {
      const channel = video.channel || '알 수 없는 채널';
      if (!acc[channel]) {
        acc[channel] = [];
      }
      acc[channel].push(video);
      return acc;
    }, {} as Record<string, VideoInfo[]>);
    
    // 각 채널의 비디오를 정렬 적용
    Object.keys(grouped).forEach(channel => {
      grouped[channel] = sortVideos(grouped[channel], sortOrder, sortDirection);
    });
    
    // 채널별로 정렬 (비디오 개수 내림차순)
    return Object.entries(grouped).sort((a, b) => b[1].length - a[1].length);
  };

    // 대시보드 렌더링 함수 개선
  const renderDashboard = () => {
    if (!appStatus) return <div>로딩 중...</div>;

    const formatNumber = (num: number) => {
      if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
      if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
      return num.toString();
    };

    const formatDuration = (seconds: number) => {
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      const paddedSeconds = remainingSeconds < 10 ? `0${remainingSeconds}` : remainingSeconds.toString();
      return `${minutes}:${paddedSeconds}`;
    };

    return (
      <div className="dashboard">
        <div className="dashboard-header">
          <div className="dashboard-stats">
            <div className="stat-card">
              <div className="stat-icon">🎥</div>
              <div className="stat-content">
                <div className="stat-number">{appStatus.total_videos}</div>
                <div className="stat-label">총 비디오</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">📺</div>
              <div className="stat-content">
                <div className="stat-number">{appStatus.total_channels}</div>
                <div className="stat-label">구독 채널</div>
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">💾</div>
              <div className="stat-content">
                <div className="stat-number">{(appStatus.vault_size_mb / 1024).toFixed(2)}GB</div>
                <div className="stat-label">보관함 크기</div>
              </div>
            </div>
          </div>
          
          <div className="dashboard-actions">
            <div className="quality-selector">
              <label htmlFor="quality-select">🎬 화질 선택:</label>
              <select 
                id="quality-select"
                value={videoQuality} 
                onChange={(e) => setVideoQuality(e.target.value)}
                className="quality-select"
              >
                <option value="480p">480p (낮음)</option>
                <option value="720p">720p (중간)</option>
                <option value="1080p">1080p (높음)</option>
                <option value="best">최고 품질</option>
              </select>
            </div>
            <button 
              onClick={downloadVideos} 
              disabled={downloadLoading}
              className={`action-btn primary ${downloadLoading ? 'loading' : ''}`}
            >
              {downloadLoading ? '📥 다운로드 중...' : '📥 비디오 다운로드'}
            </button>
            <button 
              onClick={() => setShowChannelSelector(true)} 
              disabled={embedLoading}
              className={`action-btn secondary ${embedLoading ? 'loading' : ''}`}
            >
              {embedLoading ? '🧠 벡터 생성 중...' : '🧠 벡터 생성'}
            </button>
            <button 
              onClick={checkIntegrity} 
              disabled={checkLoading}
              className={`action-btn tertiary ${checkLoading ? 'loading' : ''}`}
            >
              {checkLoading ? '🔍 검사 중...' : '🔍 정합성 검사'}
            </button>
          </div>
        </div>

        <div className="dashboard-content">
          {recentVideos.channels.map((channel, channelIndex) => {
            // 인기 비디오 (전체 기간 중 조회수 상위 5개)
            const popularVideos = [...channel.videos]
              .sort((a: VideoInfo, b: VideoInfo) => (b.view_count || 0) - (a.view_count || 0))
              .slice(0, 5);
            
            // 최신 비디오 (전체 기간 중 최신 5개)
            const latestVideos = [...channel.videos]
              .sort((a: VideoInfo, b: VideoInfo) => {
                const dateA = a.upload_date ? new Date(a.upload_date).getTime() : 0;
                const dateB = b.upload_date ? new Date(b.upload_date).getTime() : 0;
                return dateB - dateA;
              })
              .slice(0, 5);

            return (
              <div key={channelIndex} className="channel-section">
                <div className="channel-header">
                  <h2 className="channel-title">📺 {channel.channel_name}</h2>
                </div>

                <div className="channel-content">
                  {/* 인기 비디오 섹션 */}
                  <div className="video-section">
                    <h3 className="section-title">🔥 인기 비디오</h3>
                    <div className="video-list">
                      {popularVideos.map((video: VideoInfo, index: number) => (
                        <div 
                          key={`popular-${video.video_id}-${index}`} 
                          className="video-item"
                          onClick={() => {
                            setSelectedVideo(video);
                            setActiveTab('videos');
                          }}
                        >
                          <div className="video-rank">#{index + 1}</div>
                          <div className="video-details">
                            <h4 className="video-title-small">{video.title}</h4>
                            <div className="video-meta-small">
                              <span className="view-count">
                                👁️ {video.view_count ? formatNumber(video.view_count) : 'N/A'}
                              </span>
                              <span className="upload-date">
                                📅 {video.upload_date ? new Date(video.upload_date).toLocaleDateString('ko-KR') : 'N/A'}
                              </span>
                              <span className="video-duration">
                                ⏱️ {video.duration_seconds ? formatDuration(video.duration_seconds) : video.duration || 'N/A'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 최신 비디오 섹션 */}
                  <div className="video-section">
                    <h3 className="section-title">🆕 최신 비디오</h3>
                    <div className="video-list">
                      {latestVideos.map((video: VideoInfo, index: number) => (
                        <div 
                          key={`latest-${video.video_id}-${index}`} 
                          className="video-item"
                          onClick={() => {
                            setSelectedVideo(video);
                            setActiveTab('videos');
                          }}
                        >
                          <div className="video-details">
                            <h4 className="video-title-small">{video.title}</h4>
                            <div className="video-meta-small">
                              <span className="view-count">
                                👁️ {video.view_count ? formatNumber(video.view_count) : 'N/A'}
                              </span>
                              <span className="upload-date">
                                📅 {video.upload_date ? new Date(video.upload_date).toLocaleDateString('ko-KR') : 'N/A'}
                              </span>
                              <span className="video-duration">
                                ⏱️ {video.duration_seconds ? formatDuration(video.duration_seconds) : video.duration || 'N/A'}
                              </span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div style={styles.loadingContainer}>
        <div style={styles.spinner}></div>
        <div style={styles.loadingText}>Y-Data House 로딩 중...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={styles.errorContainer}>
        <div style={styles.errorIcon}>⚠️</div>
        <h2 style={styles.errorTitle}>오류가 발생했습니다</h2>
        <p style={styles.errorMessage}>{error}</p>
        <button style={styles.retryButton} onClick={loadAppData}>
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <>
      {/* 진행 상황 모달 */}
      {showProgressModal && (
        <div className="modal-overlay">
          <div className="progress-modal">
            <div className="modal-header">
              <h3>📥 비디오 다운로드 진행 상황</h3>
              <button 
                className="modal-close-btn"
                onClick={() => setShowProgressModal(false)}
                disabled={downloadLoading}
              >
                ✕
              </button>
            </div>
            
            {downloadProgress && (
              <div className="progress-info">
                <div className="progress-stats">
                  <span>📺 채널: {downloadProgress.channel}</span>
                  <span>📊 상태: {downloadProgress.status}</span>
                  <span>📈 진행률: {downloadProgress.progress.toFixed(1)}%</span>
                  <span>🎬 완료: {downloadProgress.completed_videos}/{downloadProgress.total_videos}</span>
                </div>
                
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar"
                    style={{ width: `${downloadProgress.progress}%` }}
                  />
                </div>
                
                {/* 중단 버튼 */}
                <div className="progress-actions">
                  <button 
                    className="cancel-btn"
                    onClick={cancelDownload}
                    disabled={!downloadLoading || downloadProgress?.status === "중단됨" || downloadProgress?.status === "완료"}
                  >
                    🛑 다운로드 중단
                  </button>
                </div>
              </div>
            )}
            
            <div className="logs-container">
              <h4>📋 실시간 로그</h4>
              <div className="logs-content">
                {downloadLogs.map((log, index) => (
                  <div key={index} className="log-line">
                    {log}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="modal-footer">
              {downloadLoading ? (
                <button className="btn-secondary" disabled>
                  ⏳ 다운로드 중...
                </button>
              ) : (
                <button 
                  className="btn-primary"
                  onClick={() => setShowProgressModal(false)}
                >
                  ✅ 완료
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* 채널 선택 모달 */}
      {showChannelSelector && (
        <div className="modal-overlay">
          <div className="progress-modal">
            <div className="modal-header">
              <h3>🧠 채널별 벡터 임베딩 생성</h3>
              <button 
                className="modal-close-btn"
                onClick={() => setShowChannelSelector(false)}
              >
                ✕
              </button>
            </div>
            
            <div className="channel-selector">
              <div className="channel-selector-header">
                <h4>생성할 채널을 선택하세요:</h4>
                <button 
                  onClick={toggleAllChannels}
                  className="toggle-all-btn"
                >
                  {selectedChannels.length === availableChannels.length ? '전체 해제' : '전체 선택'}
                </button>
              </div>
              
              <div className="channel-list">
                {availableChannels.map(channel => (
                  <label key={channel} className="channel-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedChannels.includes(channel)}
                      onChange={() => toggleChannelSelection(channel)}
                    />
                    <span className="channel-name">📺 {channel}</span>
                  </label>
                ))}
              </div>
              
              <div className="channel-selector-footer">
                <div className="selected-count">
                  선택됨: {selectedChannels.length} / {availableChannels.length}
                </div>
                <div className="channel-actions">
                  <button 
                    onClick={() => setShowChannelSelector(false)}
                    className="btn-secondary"
                  >
                    취소
                  </button>
                  <button 
                    onClick={createEmbeddingsForChannels}
                    disabled={selectedChannels.length === 0}
                    className="btn-primary"
                  >
                    생성 시작
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 벡터 임베딩 진행 상황 모달 */}
      {showEmbeddingModal && (
        <div className="modal-overlay">
          <div className="progress-modal">
            <div className="modal-header">
              <h3>🧠 벡터 임베딩 생성 진행 상황</h3>
              <div className="modal-header-actions">
                {embedLoading && (
                  <button 
                    onClick={cancelEmbedding}
                    className="btn-cancel"
                  >
                    🛑 중단
                  </button>
                )}
                <button 
                  className="modal-close-btn"
                  onClick={() => setShowEmbeddingModal(false)}
                  disabled={embedLoading}
                >
                  ✕
                </button>
              </div>
            </div>
            
            {embeddingProgress && (
              <div className="progress-info">
                <div className="progress-stats">
                  <span>📊 상태: {embeddingProgress.status}</span>
                  <span>📈 진행률: {embeddingProgress.progress.toFixed(1)}%</span>
                  <span>🎯 현재: {embeddingProgress.current_video}</span>
                  <span>📈 완료: {embeddingProgress.completed_videos}/{embeddingProgress.total_videos}</span>
                </div>
                
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar"
                    style={{ width: `${embeddingProgress.progress}%` }}
                  />
                </div>
                
                <div className="current-log">
                  <strong>현재 작업:</strong> {embeddingProgress.log_message}
                </div>
              </div>
            )}
            
            <div className="logs-container">
              <h4>📋 실시간 로그</h4>
              <div className="logs-content">
                {embeddingLogs.map((log, index) => (
                  <div key={index} className="log-line">
                    {log}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="modal-footer">
              {embedLoading ? (
                <button className="btn-secondary" disabled>
                  ⏳ 임베딩 생성 중...
                </button>
              ) : (
                <button 
                  className="btn-primary"
                  onClick={() => setShowEmbeddingModal(false)}
                >
                  ✅ 완료
                </button>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* 데이터 정합성 검사 진행 상황 모달 */}
      {showIntegrityModal && (
        <div className="modal-overlay">
          <div className="progress-modal">
            <div className="modal-header">
              <h3>🔍 데이터 정합성 검사 진행 상황</h3>
              <button 
                className="modal-close-btn"
                onClick={() => setShowIntegrityModal(false)}
                disabled={checkLoading}
              >
                ✕
              </button>
            </div>
            
            {integrityProgress && (
              <div className="progress-info">
                <div className="progress-stats">
                  <span>📊 상태: {integrityProgress.status}</span>
                  <span>📈 진행률: {integrityProgress.progress.toFixed(1)}%</span>
                  <span>🎯 현재: {integrityProgress.current_video}</span>
                </div>
                
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar"
                    style={{ width: `${integrityProgress.progress}%` }}
                  />
                </div>
              </div>
            )}
            
            <div className="logs-container">
              <h4>📋 실시간 로그</h4>
              <div className="logs-content">
                {integrityLogs.map((log, index) => (
                  <div key={index} className="log-line">
                    {log}
                  </div>
                ))}
              </div>
            </div>
            
            <div className="modal-footer">
              {checkLoading ? (
                <button className="btn-secondary" disabled>
                  ⏳ 검사 중...
                </button>
              ) : (
                <button 
                  className="btn-primary"
                  onClick={() => setShowIntegrityModal(false)}
                >
                  ✅ 완료
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 비디오 변환 진행 상황 모달 */}
      {showConversionModal && (
        <div className="modal-overlay">
          <div className="minimal-progress-modal">
            <div className="minimal-header">
              <span className="progress-title">🔄 변환 중</span>
              <div className="header-actions">
                {conversionLoading && (
                  <button 
                    onClick={cancelConversion}
                    className="minimal-btn cancel"
                  >
                    🛑
                  </button>
                )}
                <button 
                  className="minimal-btn close"
                  onClick={() => setShowConversionModal(false)}
                  disabled={conversionLoading}
                >
                  ✕
                </button>
              </div>
            </div>
            
            {conversionProgress && (
              <div className="minimal-progress">
                <div className="video-name">
                  {selectedVideo?.title?.substring(0, 50) || conversionProgress.current_video}
                  {(selectedVideo?.title?.length || 0) > 50 && '...'}
                </div>
                <div className="progress-bar-container">
                  <div 
                    className="progress-bar"
                    style={{ 
                      width: conversionProgress.progress > 0 ? `${conversionProgress.progress}%` : '20%',
                      background: conversionProgress.progress > 0 ? '#4CAF50' : '#2196F3'
                    }}
                  />
                </div>
                <div className="progress-text">
                  {conversionProgress.progress > 0 
                    ? `${conversionProgress.progress.toFixed(1)}%` 
                    : '진행 중...'}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
      
      <div className="container">
      <header className="header">
        <h1>🎥 Y-Data-House Desktop</h1>
        <p>YouTube 비디오 분석 및 지식 관리 도구</p>
      </header>

      <nav className="tab-nav">
        {[
          { id: 'dashboard', icon: '📊', label: '대시보드' },
          { id: 'channels', icon: '📺', label: '채널 관리' },
          { id: 'videos', icon: '🎬', label: '비디오 목록' },
          { id: 'search', icon: '🔍', label: '벡터 검색' },
          { id: 'ai', icon: '🤖', label: 'AI 질문' },
          { id: 'settings', icon: '⚙️', label: '설정' }
        ].map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as TabType)}
            className={activeTab === tab.id ? 'active' : ''}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </nav>

      <main className="main-content">
        {activeTab === 'dashboard' && renderDashboard()}

        {activeTab === 'channels' && (
          <div className="tab-content">
            <h2 className="tab-title">📺 채널 관리</h2>
            
            <div className="channel-add-section">
              <input
                type="text"
                value={newChannelUrl}
                onChange={(e) => setNewChannelUrl(e.target.value)}
                placeholder="YouTube 채널 URL을 입력하세요 (예: https://www.youtube.com/@채널명)"
                className="channel-input"
                onKeyPress={(e) => e.key === 'Enter' && addChannel()}
              />
              <button onClick={addChannel} className="add-channel-button">
                ➕ 채널 추가
              </button>
            </div>

            <div className="channel-list">
              {channels.length > 0 ? (
                channels.map((channel, index) => (
                  <div key={index} className="channel-item">
                    <div className="channel-info">
                      <div className="channel-name">
                        {channel.enabled ? '✅' : '❌'} {channel.name}
                      </div>
                      <div className="channel-url">{channel.url}</div>
                    </div>
                    <div className="channel-actions">
                      <button 
                        onClick={() => toggleChannel(channel.url)}
                        className="channel-toggle-button"
                      >
                        {channel.enabled ? '⏸️ 비활성화' : '▶️ 활성화'}
                      </button>
                      <button 
                        onClick={() => removeChannel(channel.url)}
                        className="channel-remove-button"
                      >
                        🗑️ 삭제
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="no-channels">
                  <div className="no-selection-icon">📺</div>
                  <h3>등록된 채널이 없습니다</h3>
                  <p>위에서 YouTube 채널 URL을 입력하여 채널을 추가하세요</p>
                  <p className="example-text">예: https://www.youtube.com/@채널명</p>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'videos' && (
          <div className="tab-content">
            <h2 className="tab-title">🎬 비디오 목록</h2>
            
            {/* 검색 및 정렬 컨트롤 */}
            <div className="video-controls">
              <div className="search-controls">
                <div className="keyword-search">
                  <input
                    type="text"
                    value={keywordSearchQuery}
                    onChange={(e) => setKeywordSearchQuery(e.target.value)}
                    placeholder="제목, 채널명, 태그로 검색..."
                    className="keyword-search-input"
                    onKeyPress={(e) => e.key === 'Enter' && performKeywordSearch()}
                  />
                  <button onClick={performKeywordSearch} className="keyword-search-button">
                    🔍 검색
                  </button>
                  {keywordSearchQuery && (
                    <button 
                      onClick={() => {
                        setKeywordSearchQuery('');
                        setKeywordSearchResults([]);
                        setFilteredVideos(videos);
                      }} 
                      className="clear-search-button"
                    >
                      ✕ 초기화
                    </button>
                  )}
                </div>
              </div>
              
              <div className="sort-controls">
                <label className="sort-label">정렬:</label>
                <button 
                  onClick={() => handleSortChange('date')}
                  className={`sort-button ${sortOrder === 'date' ? 'active' : ''}`}
                >
                  📅 날짜 {sortOrder === 'date' && (sortDirection === 'desc' ? '↓' : '↑')}
                </button>
                <button 
                  onClick={() => handleSortChange('title')}
                  className={`sort-button ${sortOrder === 'title' ? 'active' : ''}`}
                >
                  📝 제목 {sortOrder === 'title' && (sortDirection === 'desc' ? '↓' : '↑')}
                </button>
                <button 
                  onClick={() => handleSortChange('views')}
                  className={`sort-button ${sortOrder === 'views' ? 'active' : ''}`}
                >
                  👁️ 조회수 {sortOrder === 'views' && (sortDirection === 'desc' ? '↓' : '↑')}
                </button>
                <button 
                  onClick={() => handleSortChange('duration')}
                  className={`sort-button ${sortOrder === 'duration' ? 'active' : ''}`}
                >
                  ⏱️ 길이 {sortOrder === 'duration' && (sortDirection === 'desc' ? '↓' : '↑')}
                </button>
              </div>
            </div>

            {/* 검색 결과 표시 */}
            {keywordSearchQuery && (
              <div className="search-result-info">
                <p>"{keywordSearchQuery}" 검색 결과: {filteredVideos.length}개 비디오</p>
              </div>
            )}
            
            <div className="video-layout">
              <div className="video-sidebar">
                <h3 className="sidebar-title">
                  비디오 목록 ({filteredVideos.length}개
                  {keywordSearchQuery && `/${videos.length}개`})
                </h3>
                <div className="video-list">
                  {groupVideosByChannel(filteredVideos).map(([channelName, channelVideos]) => (
                    <div key={channelName} className="channel-group">
                      <div 
                        className="channel-group-header"
                        onClick={() => toggleChannelCollapse(channelName)}
                      >
                        <span className="channel-toggle-icon">
                          {collapsedChannels.has(channelName) ? '▶️' : '🔽'}
                        </span>
                        <span className="channel-group-name">📺 {channelName}</span>
                        <span className="channel-video-count">({channelVideos.length}개)</span>
                      </div>
                      
                      {!collapsedChannels.has(channelName) && (
                        <div className="channel-videos">
                          {channelVideos.map((video, index) => (
                            <div
                              key={`${channelName}-${index}`}
                              className={`video-item ${selectedVideo && (selectedVideo.video_id === video.video_id || selectedVideo.video_path === video.video_path) ? 'video-item-active' : ''}`}
                              onClick={() => setSelectedVideo(video)}
                            >
                              {video.upload_date && (
                                <div className="video-date-small">📅 {video.upload_date}</div>
                              )}
                              <div className="video-title">{video.title}</div>
                              <div className="video-meta-row">
                                {video.duration && (
                                  <div className="video-duration">⏱️ {video.duration}</div>
                                )}
                                {video.view_count && (
                                  <div className="video-views">👁️ {video.view_count.toLocaleString()}</div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div className="video-main">
                {selectedVideo ? (
                  <>
                    {/* 서버 로딩 상태만 표시 (미니멀) */}
                    {serverLoading && (
                      <div className="server-status-minimal">
                        <span className="status-minimal">🟡 비디오 서버 시작 중...</span>
                      </div>
                    )}

                    {/* 비디오 플레이어 */}
                    {videoUrl ? (
                      <div className="video-container">
                        <video
                          key={videoUrl} // URL 변경 시 비디오 엘리먼트 강제 리렌더링
                          src={videoUrl}
                          controls
                          className="video-player"
                          preload="metadata"
                          style={{ width: '100%', height: 'auto' }}
                          onError={handleVideoError}
                          onLoadStart={() => {
                            setVideoError(null); // 로딩 시작 시 에러 초기화
                          }}
                          onCanPlay={() => {
                            setVideoError(null); // 재생 가능 시 에러 초기화
                          }}
                        >
                          비디오를 로드할 수 없습니다.
                        </video>
                        
                                                 {/* 비디오 에러 표시 및 대체 방안 */}
                         {videoError && (
                           <div style={styles.videoErrorContainer}>
                             <div style={styles.videoError}>
                               <div style={styles.videoErrorIcon}>⚠️</div>
                               <div style={styles.errorContent}>
                                 <h4>비디오 재생 문제</h4>
                                 <p>{videoError}</p>

                                 <div style={styles.errorButtonGroup}>
                                   <button 
                                     onClick={openInSystemPlayer}
                                     style={styles.systemPlayerButton}
                                   >
                                     🎬 시스템 플레이어로 열기
                                   </button>
                                   <button 
                                     onClick={() => convertVideo()}
                                     disabled={conversionLoading}
                                     style={{...styles.systemPlayerButton, backgroundColor: '#ff6b47'}}
                                   >
                                     {conversionLoading ? '🔄 변환 중...' : '🔄 H.264로 변환'}
                                   </button>
                                 </div>
                               </div>
                             </div>
                           </div>
                         )}
                      </div>
                    ) : videoServerPort ? (
                      <div className="video-loading">
                        <div className="loading-spinner">⏳</div>
                        <p>비디오 URL 생성 중...</p>
                      </div>
                    ) : (
                      <div className="server-required">
                        <div className="server-icon">🎬</div>
                        <h3>비디오 자동 로딩 중</h3>
                        <p>비디오 서버를 자동으로 시작하고 있습니다.<br/>잠시만 기다려주세요...</p>
                        <div className="loading-spinner">⏳</div>
                      </div>
                    )}

                    <div className="video-info">
                      <h3 className="video-title-main">{selectedVideo.title}</h3>
                      <p className="video-channel-main">{selectedVideo.channel}</p>
                      {selectedVideo.upload_date && (
                        <p className="video-upload-date">업로드: {selectedVideo.upload_date}</p>
                      )}
                    </div>

                    <div className="caption-search">
                      <h4 className="section-title">📝 자막 내용</h4>
                      
                      {/* 자막 필터링 섹션 */}
                      <div className="caption-filter-section">
                        <div className="caption-filter-controls">
                          <input
                            type="text"
                            value={captionFilter}
                            onChange={(e) => setCaptionFilter(e.target.value)}
                            placeholder="자막에서 검색..."
                            className="caption-filter-input"
                            onKeyPress={(e) => e.key === 'Enter' && applyCaptionFilter()}
                          />
                          <button onClick={applyCaptionFilter} className="caption-filter-button">
                            🔍 필터
                          </button>
                          {captionFilter && (
                            <button onClick={clearCaptionFilter} className="caption-clear-button">
                              ✕ 초기화
                            </button>
                          )}
                        </div>
                      </div>
                      
                      {/* 자막 컨테이너 */}
                      <div className="captions-container">
                        <div className="captions-header">
                          <div className="captions-title">
                            📋 자막 목록
                            <span className="captions-count">
                              {filteredCaptions.length > 0 ? filteredCaptions.length : captions.length}개
                            </span>
                          </div>
                          <div className="captions-controls">
                            <button 
                              onClick={copyAllCaptions}
                              className="caption-copy-button"
                              disabled={captions.length === 0 || captionLoading}
                              title="전체 자막 복사"
                            >
                              📋
                            </button>
                          </div>
                        </div>
                        
                        <div className="captions-content">
                          {captionLoading ? (
                            <div className="captions-loading">
                              <div className="captions-loading-spinner">⏳</div>
                              <div className="captions-loading-text">자막 로딩 중...</div>
                            </div>
                          ) : (filteredCaptions.length > 0 ? filteredCaptions : captions).length > 0 ? (
                            (filteredCaptions.length > 0 ? filteredCaptions : captions).map((caption) => (
                              <div 
                                key={caption.index} 
                                className={`caption-item ${highlightedCaptions.has(caption.index) ? 'highlighted' : ''}`}
                                data-caption-index={caption.index}
                                onClick={() => setCurrentCaptionIndex(caption.index)}
                              >
                                <div className="caption-header">
                                  <span className="caption-index">#{caption.index + 1}</span>
                                  {caption.timestamp && (
                                    <span className="caption-timestamp">
                                      {caption.timestamp}
                                    </span>
                                  )}
                                </div>
                                <div 
                                  className="caption-text"
                                  dangerouslySetInnerHTML={{
                                    __html: getHighlightedText(caption.content, captionFilter)
                                  }}
                                />
                              </div>
                            ))
                          ) : (
                            <div className="no-captions">
                              <div className="no-captions-icon">📝</div>
                              <h3>자막이 없습니다</h3>
                              <p>이 비디오에는 자막 정보가 없거나</p>
                              <p>자막 파일을 읽을 수 없습니다.</p>
                              <p className="no-captions-help">자막 파일 경로를 확인해주세요.</p>
                            </div>
                          )}
                        </div>

                      </div>
                    </div>
                  </>
                ) : (
                  <div className="no-selection">
                    <div className="no-selection-icon">🎬</div>
                    <h3>비디오를 선택하세요</h3>
                    <p>왼쪽 목록에서 비디오를 클릭하여 재생하고 캡션을 확인하세요</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'search' && (
          <div className="tab-content">
            <h2 className="tab-title">🔍 벡터 검색</h2>
            
            <div className="search-section">
              <h3 className="section-title">전체 비디오에서 검색</h3>
              <div className="search-container">
                <input
                  type="text"
                  value={vectorSearchQuery}
                  onChange={(e) => setVectorSearchQuery(e.target.value)}
                  placeholder="모든 비디오의 캡션에서 검색할 내용을 입력하세요..."
                  className="search-input"
                  onKeyPress={(e) => e.key === 'Enter' && performVectorSearch()}
                />
                <button onClick={performVectorSearch} className="search-button">
                  🔍 벡터 검색
                </button>
              </div>
              
              {vectorSearchResults && (
                <div className="search-results">
                  <h4 className="results-title">검색 결과:</h4>
                  <pre className="results-text">{vectorSearchResults}</pre>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'ai' && (
          <div className="tab-content">
            <h2 className="tab-title">🤖 AI 질문하기</h2>
            
            <div className="ai-section">
              <h3 className="section-title">DeepSeek RAG 시스템</h3>
              <div className="ai-input-container">
                <textarea
                  value={aiQuestion}
                  onChange={(e) => setAiQuestion(e.target.value)}
                  placeholder="비디오 내용에 대해 궁금한 것을 질문하세요. 예: '부동산 투자 시 주의할 점은?', '도쿄 원룸 투자 수익률은?'"
                  className="ai-input"
                  rows={4}
                />
                <button 
                  onClick={askAI} 
                  disabled={aiLoading || !aiQuestion.trim()}
                  className={`ai-button ${aiLoading ? 'ai-button-loading' : ''}`}
                >
                  {aiLoading ? '🤔 생각하는 중...' : '💬 질문하기'}
                </button>
              </div>
              
              {aiAnswer && (
                <div className="ai-answer">
                  <h4 className="answer-title">AI 답변:</h4>
                  <pre className="answer-text">{aiAnswer}</pre>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="tab-content">
            <h2 className="tab-title">⚙️ 설정</h2>
            
            <div className="settings-grid">
              <div className="settings-card">
                <h3 className="card-title">🗂️ 프로젝트 정보</h3>
                <div className="card-content">
                  <div className="setting-item">
                    <span>프로젝트:</span>
                    <span>Y-Data-House</span>
                  </div>
                  <div className="setting-item">
                    <span>버전:</span>
                    <span>1.0.0</span>
                  </div>
                  <div className="setting-item">
                    <span>Vault 경로:</span>
                    <span>../vault</span>
                  </div>
                  <div className="setting-item">
                    <span>채널 설정:</span>
                    <span>../channels.txt</span>
                  </div>
                </div>
              </div>

              <div className="settings-card">
                <h3 className="card-title">🔧 도구 정보</h3>
                <div className="card-content">
                  <div className="setting-item">
                    <span>Frontend:</span>
                    <span>React + TypeScript</span>
                  </div>
                  <div className="setting-item">
                    <span>Backend:</span>
                    <span>Tauri + Rust</span>
                  </div>
                  <div className="setting-item">
                    <span>Python CLI:</span>
                    <span>ydh 패키지</span>
                  </div>
                  <div className="setting-item">
                    <span>AI:</span>
                    <span>DeepSeek + ChromaDB</span>
                  </div>
                </div>
              </div>

              <div className="settings-card">
                <h3 className="card-title">📚 사용법</h3>
                <div className="card-content">
                  <div className="usage-step">
                    <strong>1.</strong> 채널 관리에서 YouTube 채널 추가
                  </div>
                  <div className="usage-step">
                    <strong>2.</strong> 대시보드에서 비디오 다운로드
                  </div>
                  <div className="usage-step">
                    <strong>3.</strong> 벡터 임베딩 생성
                  </div>
                  <div className="usage-step">
                    <strong>4.</strong> 검색 또는 AI 질문 활용
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
    </>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column' as const,
    height: '100vh',
    backgroundColor: '#0f0f0f',
    color: '#ffffff',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  
  header: {
    backgroundColor: '#1a1a1a',
    borderBottom: '1px solid #333',
    padding: '16px 24px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  
  headerContent: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
  },
  
  title: {
    margin: 0,
    fontSize: '24px',
    fontWeight: 700,
    background: 'linear-gradient(135deg, #ff4757, #3742fa)',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: 'transparent',
  },
  
  subtitle: {
    color: '#888',
    fontSize: '14px',
  },
  
  headerStats: {
    display: 'flex',
    gap: '24px',
  },
  
  stat: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    gap: '4px',
  },
  
  statValue: {
    fontSize: '20px',
    fontWeight: 600,
    color: '#fff',
  },
  
  statLabel: {
    fontSize: '12px',
    color: '#888',
  },
  
  nav: {
    backgroundColor: '#1a1a1a',
    borderBottom: '1px solid #333',
    padding: '0 24px',
    display: 'flex',
    gap: '8px',
  },
  
  tabButton: {
    padding: '12px 20px',
    background: 'none',
    border: 'none',
    color: '#888',
    fontSize: '14px',
    fontWeight: 500,
    cursor: 'pointer',
    borderBottom: '2px solid transparent',
    transition: 'all 0.2s ease',
  },
  
  tabButtonActive: {
    color: '#fff',
    borderBottomColor: '#3742fa',
  },
  
  main: {
    flex: 1,
    overflow: 'auto',
    padding: '24px',
  },
  
  tabContent: {
    maxWidth: '1200px',
    margin: '0 auto',
  },
  
  tabTitle: {
    margin: '0 0 24px 0',
    fontSize: '28px',
    fontWeight: 600,
  },
  
  // Dashboard styles
  dashboardGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '24px',
  },
  
  dashboardCard: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '12px',
    padding: '20px',
  },
  
  cardTitle: {
    margin: '0 0 16px 0',
    fontSize: '18px',
    fontWeight: 600,
  },
  
  cardContent: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
  },
  
  statusItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  
  actionButton: {
    padding: '12px 16px',
    backgroundColor: '#3742fa',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background-color 0.2s ease',
  },
  
  recentVideo: {
    padding: '8px 0',
    borderBottom: '1px solid #333',
  },
  
  recentVideoTitle: {
    fontSize: '14px',
    fontWeight: 500,
    marginBottom: '4px',
  },
  
  recentVideoChannel: {
    fontSize: '12px',
    color: '#888',
  },
  
  // Channel styles
  channelAddSection: {
    display: 'flex',
    gap: '12px',
    marginBottom: '24px',
  },
  
  channelInput: {
    flex: 1,
    padding: '12px 16px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    color: '#fff',
    fontSize: '14px',
    outline: 'none',
  },
  
  addChannelButton: {
    padding: '12px 20px',
    backgroundColor: '#2ed573',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  
  channelList: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '12px',
  },
  
  channelItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '16px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
  },
  
  channelInfo: {
    flex: 1,
  },
  
  channelName: {
    fontSize: '16px',
    fontWeight: 500,
    marginBottom: '4px',
  },
  
  channelUrl: {
    fontSize: '12px',
    color: '#888',
  },
  
  channelActions: {
    display: 'flex',
    gap: '8px',
  },
  
  channelToggleButton: {
    padding: '8px 12px',
    backgroundColor: '#ffa502',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  
  channelRemoveButton: {
    padding: '8px 12px',
    backgroundColor: '#ff4757',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '12px',
    cursor: 'pointer',
  },
  
  // Video styles
  videoLayout: {
    display: 'flex',
    gap: '24px',
    height: 'calc(100vh - 200px)',
  },
  
  videoSidebar: {
    width: '300px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '16px',
    display: 'flex',
    flexDirection: 'column' as const,
  },
  
  sidebarTitle: {
    margin: '0 0 16px 0',
    fontSize: '16px',
    fontWeight: 600,
  },
  
  videoList: {
    flex: 1,
    overflowY: 'auto' as const,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '8px',
  },
  
  videoItem: {
    padding: '12px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
  },
  
  videoItemActive: {
    backgroundColor: '#3742fa',
    borderColor: '#5352ed',
  },
  
  videoTitle: {
    fontSize: '14px',
    fontWeight: 500,
    marginBottom: '4px',
    lineHeight: 1.3,
  },
  
  videoChannel: {
    fontSize: '12px',
    color: '#888',
    marginBottom: '2px',
  },
  
  videoDate: {
    fontSize: '11px',
    color: '#666',
  },
  
  videoMain: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '20px',
  },
  
  videoPlayer: {
    width: '100%',
    maxHeight: '400px',
    borderRadius: '8px',
    backgroundColor: '#000',
  },
  
  videoInfo: {
    padding: '16px',
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
  },
  
  videoTitleMain: {
    margin: '0 0 8px 0',
    fontSize: '20px',
    fontWeight: 600,
  },
  
  videoChannelMain: {
    margin: '0 0 4px 0',
    color: '#888',
    fontSize: '14px',
  },
  
  videoUploadDate: {
    margin: 0,
    color: '#666',
    fontSize: '12px',
  },
  
  captionSearch: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '16px',
  },
  
  sectionTitle: {
    margin: '0 0 16px 0',
    fontSize: '16px',
    fontWeight: 600,
  },
  
  searchContainer: {
    display: 'flex',
    gap: '12px',
    marginBottom: '16px',
  },
  
  searchInput: {
    flex: 1,
    padding: '10px 12px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    outline: 'none',
  },
  
  searchButton: {
    padding: '10px 16px',
    backgroundColor: '#ff4757',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  
  captionsContainer: {
    maxHeight: '200px',
    overflowY: 'auto' as const,
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
  },
  
  captionLine: {
    display: 'flex',
    padding: '8px 12px',
    borderBottom: '1px solid #333',
    gap: '12px',
  },
  
  captionIndex: {
    color: '#888',
    fontSize: '12px',
    minWidth: '30px',
    textAlign: 'right' as const,
  },
  
  captionText: {
    flex: 1,
    fontSize: '13px',
    lineHeight: 1.4,
  },
  
  noSelection: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    textAlign: 'center' as const,
    color: '#888',
  },
  
  noSelectionIcon: {
    fontSize: '64px',
    marginBottom: '16px',
  },
  
  // Search styles
  searchSection: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '20px',
  },
  
  searchResults: {
    marginTop: '20px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    padding: '16px',
  },
  
  resultsTitle: {
    margin: '0 0 12px 0',
    fontSize: '16px',
    fontWeight: 600,
    color: '#2ed573',
  },
  
  resultsText: {
    margin: 0,
    fontSize: '13px',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
  },
  
  // AI styles
  aiSection: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '20px',
  },
  
  aiInputContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: '16px',
  },
  
  aiInput: {
    padding: '12px 16px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    color: '#fff',
    fontSize: '14px',
    outline: 'none',
    resize: 'vertical' as const,
    minHeight: '100px',
  },
  
  aiButton: {
    alignSelf: 'flex-start',
    padding: '12px 24px',
    backgroundColor: '#2ed573',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background-color 0.2s ease',
  },
  
  aiButtonLoading: {
    backgroundColor: '#888',
    cursor: 'not-allowed',
  },
  
  aiAnswer: {
    marginTop: '20px',
    backgroundColor: '#0f0f0f',
    border: '1px solid #333',
    borderRadius: '6px',
    padding: '16px',
  },
  
  answerTitle: {
    margin: '0 0 12px 0',
    fontSize: '16px',
    fontWeight: 600,
    color: '#2ed573',
  },
  
  answerText: {
    margin: 0,
    fontSize: '13px',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
  },
  
  // Settings styles
  settingsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: '24px',
  },
  
  settingsCard: {
    backgroundColor: '#1a1a1a',
    border: '1px solid #333',
    borderRadius: '8px',
    padding: '20px',
  },
  
  settingItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 0',
    borderBottom: '1px solid #333',
  },
  
  usageStep: {
    padding: '8px 0',
    fontSize: '14px',
    lineHeight: 1.4,
  },
  
  // Loading and error styles
  loadingContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    backgroundColor: '#0f0f0f',
    color: '#ffffff',
  },
  
  spinner: {
    width: '40px',
    height: '40px',
    border: '4px solid #333',
    borderTop: '4px solid #3742fa',
    borderRadius: '50%',
    animation: 'spin 1s linear infinite',
    marginBottom: '16px',
  },
  
  loadingText: {
    fontSize: '16px',
    color: '#888',
  },
  
  errorContainer: {
    display: 'flex',
    flexDirection: 'column' as const,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100vh',
    backgroundColor: '#0f0f0f',
    color: '#ffffff',
    textAlign: 'center' as const,
  },
  
  errorIcon: {
    fontSize: '64px',
    marginBottom: '24px',
  },
  
  errorTitle: {
    margin: '0 0 16px 0',
    fontSize: '28px',
    fontWeight: 600,
    color: '#ff4757',
  },
  
  errorMessage: {
    margin: '0 0 24px 0',
    color: '#888',
    fontSize: '16px',
    maxWidth: '400px',
  },
  
  retryButton: {
    padding: '12px 24px',
    backgroundColor: '#3742fa',
    color: 'white',
    border: 'none',
    borderRadius: '8px',
    fontSize: '16px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  
  // 비디오 에러 스타일
  videoErrorContainer: {
    marginTop: '16px',
  },
  
  videoError: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
    padding: '16px',
    backgroundColor: '#2c1810',
    border: '1px solid #ff6b47',
    borderRadius: '8px',
    color: '#fff',
  },
  
  videoErrorIcon: {
    fontSize: '24px',
    flexShrink: 0,
  },
  
  errorContent: {
    flex: 1,
  },
  
  codecHelp: {
    marginTop: '12px',
    padding: '12px',
    backgroundColor: '#1a1a1a',
    borderRadius: '6px',
    fontSize: '13px',
  },
  
  systemPlayerButton: {
    marginTop: '12px',
    padding: '8px 16px',
    backgroundColor: '#2ed573',
    color: 'white',
    border: 'none',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background-color 0.2s ease',
  },
  
  errorButtonGroup: {
    display: 'flex',
    gap: '8px',
    flexWrap: 'wrap' as const,
    alignItems: 'center',
  },
  };
