import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import MiniOrb from './MiniOrb';
import './index.css';

const miniOrb = new URLSearchParams(window.location.search).get('view') === 'orb';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {miniOrb ? <MiniOrb /> : <App />}
  </React.StrictMode>,
);
