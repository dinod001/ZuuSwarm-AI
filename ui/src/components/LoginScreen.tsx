import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Bot, ShieldCheck, Activity, Lock, BrainCircuit, Zap } from 'lucide-react';

interface LoginScreenProps {
  onLogin: (email: string) => void;
  onBack?: () => void;
}

export const LoginScreen: React.FC<LoginScreenProps> = ({ onLogin, onBack }) => {
  const [email, setEmail] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email.trim()) {
      onLogin(email.trim());
    }
  };

  return (
    <div className="login-v2-container">
      {/* ── Animated Background Enhancements ── */}
      <div className="v2-bg-grid" />
      <div className="v2-glow-orb orb-amber" />
      <div className="v2-glow-orb orb-cyan" />

      <div className="login-v2-wrapper">
        {/* ── Left Side: Content & Branding ── */}
        <div className="login-v2-left">
        <div className="login-brand-top">
          <img src="/logo.png" alt="ZuuSwarm AI" />
          <span>ZuuSwarm AI</span>
        </div>
        
        <div className="login-v2-hero-content">
          <div className="status-badge-v2">
            <span className="pulse-dot-green" /> Systems Operational
          </div>
          
          <h1 className="login-h1">Autonomous IT Operations,<br/>Powered by <span className="text-gradient">AI</span></h1>
          <p className="login-p">Investigate incidents, manage infrastructure, and resolve issues faster with your swarm of intelligent AI agents.</p>
          
          <div className="stats-row">
            <div className="stat-box">
              <div className="stat-icon-wrapper orange">
                <span className="stat-emoji"><Bot size={18} /></span>
              </div>
              <div className="stat-text">
                <strong>24</strong>
                <span>Active Agents</span>
              </div>
            </div>
            <div className="stat-box">
              <div className="stat-icon-wrapper teal">
                <span className="stat-emoji"><ShieldCheck size={18} /></span>
              </div>
              <div className="stat-text">
                <strong>156</strong>
                <span>Incidents Resolved</span>
              </div>
            </div>
            <div className="stat-box">
              <div className="stat-icon-wrapper blue">
                <span className="stat-emoji"><Activity size={18} /></span>
              </div>
              <div className="stat-text">
                <strong>99.98%</strong>
                <span>Uptime (30d)</span>
              </div>
            </div>
          </div>
          
          <div className="hero-description-block">
            <h3>Enterprise-Grade Intelligence</h3>
            <p>
              Experience the next generation of IT operations. ZuuSwarm AI continuously monitors your infrastructure, proactively resolves incidents, and optimizes system performance in real-time without human intervention. 
            </p>
            <p>
              Our advanced neural swarm architecture guarantees zero downtime and automated threat neutralization, allowing your engineering teams to focus purely on innovation.
            </p>
          </div>
        </div>
        
        <div className="login-v2-footer-features">
          <div className="feature-item">
            <span className="feat-icon"><Lock size={16} /></span>
            <div className="feat-text">
              <strong>Enterprise Grade Security</strong>
              <span>SOC 2 Type II Compliant</span>
            </div>
          </div>
          <div className="feature-item">
            <span className="feat-icon"><BrainCircuit size={16} /></span>
            <div className="feat-text">
              <strong>AI-Powered Automation</strong>
              <span>Built for Modern IT Teams</span>
            </div>
          </div>
          <div className="feature-item">
            <span className="feat-icon"><Zap size={16} /></span>
            <div className="feat-text">
              <strong>Real-time Intelligence</strong>
              <span>Detect. Investigate. Resolve.</span>
            </div>
          </div>
        </div>
      </div>
      
      {/* ── Right Side: Floating Login Card ── */}
      <div className="login-v2-right">
        <motion.div 
          className="login-v2-card"
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="card-header">
            <img src="/logo.png" alt="ZuuSwarm AI" className="card-logo" />
            <h2>Welcome Back</h2>
            <p>Sign in to access your AI operations console</p>
          </div>
          
          <form onSubmit={handleSubmit} className="login-form-v2">
            <div className="form-group-v2">
              <label>Work Email</label>
              <div className="input-with-icon-v2">
                <span className="input-icon-svg">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>
                </span>
                <input 
                  type="email" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com" 
                  required
                  autoFocus
                />
              </div>
            </div>
            
            <button type="submit" className="btn-primary-v2" disabled={!email.trim()}>
              Continue <span className="arrow-right">→</span>
            </button>
            
            <p className="request-invite">
              Need access? <a href="#">Request an invite</a>
            </p>

            {onBack && (
              <button
                className="login-back-link"
                onClick={onBack}
                type="button"
                style={{ marginTop: '1.5rem', width: '100%', textAlign: 'center' }}
              >
                ← Back to home
              </button>
            )}
          </form>
        </motion.div>
      </div>
      </div>
    </div>
  );
};
