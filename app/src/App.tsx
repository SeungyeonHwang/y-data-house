import React from 'react';

export default function App() {
  return (
    <div style={{ 
      display: 'flex', 
      justifyContent: 'center', 
      alignItems: 'center', 
      height: '100vh', 
      fontFamily: 'sans-serif',
      backgroundColor: '#f0f0f0'
    }}>
      <div style={{ textAlign: 'center' }}>
        <h1 style={{ color: '#333' }}>🎉 YDH Desktop 앱이 실행되었습니다!</h1>
        <p style={{ color: '#666' }}>React와 Tauri가 정상적으로 연결되었습니다.</p>
        <button 
          onClick={() => alert('버튼이 클릭되었습니다!')}
          style={{
            padding: '10px 20px',
            fontSize: '16px',
            backgroundColor: '#007acc',
            color: 'white',
            border: 'none',
            borderRadius: '5px',
            cursor: 'pointer'
          }}
        >
          테스트 버튼
        </button>
      </div>
    </div>
  );
}
