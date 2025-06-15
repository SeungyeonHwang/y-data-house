import React, { useEffect, useState } from 'react';
import { invoke } from '@tauri-apps/api/core';
import { convertFileSrc } from '@tauri-apps/api/core';
import Fuse from 'fuse.js';

interface VideoInfo {
  video_path: string;
  captions_path: string;
}

interface CaptionLine {
  index: number;
  content: string;
}

export default function App() {
  const [videos, setVideos] = useState<VideoInfo[]>([]);
  const [selected, setSelected] = useState<VideoInfo | null>(null);
  const [captions, setCaptions] = useState<CaptionLine[]>([]);
  const [fuse, setFuse] = useState<Fuse<CaptionLine>>();
  const [search, setSearch] = useState('');
  const [results, setResults] = useState<CaptionLine[]>([]);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');

  useEffect(() => {
    invoke<VideoInfo[]>('list_videos').then(setVideos);
  }, []);

  useEffect(() => {
    if (!selected) {
      setCaptions([]);
      setFuse(undefined);
      return;
    }
    fetch(convertFileSrc(selected.captions_path))
      .then((r) => r.text())
      .then((text) => {
        const lines = text.split(/\r?\n/).filter(Boolean);
        const docs = lines.map((content, index) => ({ index, content }));
        setCaptions(docs);
        setFuse(new Fuse(docs, { keys: ['content'], threshold: 0.3 }));
      })
      .catch((error) => {
        console.error('Failed to read captions file:', error);
      });
  }, [selected]);

  const onSearch = () => {
    if (!fuse || search.length < 2) {
      setResults([]);
      return;
    }
    setResults(fuse.search(search).map((x) => x.item));
  };

  const onAsk = async () => {
    const resp = await invoke<string>('ask_rag', { query: question });
    setAnswer(resp);
  };

  return (
    <div style={{ display: 'flex', height: '100vh', fontFamily: 'sans-serif' }}>
      <aside style={{ width: 250, borderRight: '1px solid #ccc', padding: 10, overflowY: 'auto' }}>
        <h3>Videos</h3>
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {videos.map((v) => (
            <li key={v.video_path} style={{ marginBottom: 4 }}>
              <button onClick={() => setSelected(v)} style={{ width: '100%', textAlign: 'left' }}>
                {v.video_path.split('/').slice(-2, -1)[0]}
              </button>
            </li>
          ))}
        </ul>
      </aside>
      <main style={{ flex: 1, padding: 10, overflowY: 'auto' }}>
        {selected && (
          <>
            <video
              key={selected.video_path}
              src={convertFileSrc(selected.video_path)}
              controls
              style={{ width: '100%', maxHeight: 400 }}
            />
            <div style={{ marginTop: 10 }}>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search captions"
              />
              <button onClick={onSearch}>Search</button>
            </div>
            <ul>
              {(results.length > 0 ? results : captions).map((line) => (
                <li key={line.index}>{line.content}</li>
              ))}
            </ul>
          </>
        )}
        <hr />
        <div>
          <textarea
            rows={4}
            style={{ width: '100%' }}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask DeepSeek"
          />
          <button onClick={onAsk}>Ask</button>
          <pre>{answer}</pre>
        </div>
      </main>
    </div>
  );
}
