import React from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, Lock, Activity, Bot, TrendingUp, Zap, Sparkles, Mic, BarChart3, Fingerprint, Search, Wrench, ClipboardCheck } from 'lucide-react';

interface LandingPageProps {
  onGoToLogin: () => void;
}

// ── Animation Variants ──
const fadeDown = {
  hidden: { opacity: 0, y: -30 },
  visible: { opacity: 1, y: 0 },
};

const fadeUp = {
  hidden: { opacity: 0, y: 40 },
  visible: { opacity: 1, y: 0 },
};

const fadeLeft = {
  hidden: { opacity: 0, x: -40 },
  visible: { opacity: 1, x: 0 },
};

const fadeRight = {
  hidden: { opacity: 0, x: 40 },
  visible: { opacity: 1, x: 0 },
};

const scaleReveal = {
  hidden: { opacity: 0, scale: 0.85 },
  visible: { opacity: 1, scale: 1 },
};

const staggerContainer = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.15,
      delayChildren: 0.1,
    },
  },
};

const cardVariant = {
  hidden: { opacity: 0, y: 30, scale: 0.97 },
  visible: { opacity: 1, y: 0, scale: 1 },
};

const ease = [0.22, 1, 0.36, 1] as const;

// ── Technical Background Waves ──
const TechWaveBackground = () => (
  <div className="tech-wave-container">
    {/* EKG Heart Rate Line */}
    <svg className="tech-wave-svg wave-1" viewBox="0 0 1000 100" preserveAspectRatio="none">
      <path 
        className="wave-track"
        d="M 0 50 L 200 50 L 220 20 L 240 80 L 260 50 L 450 50 L 470 10 L 510 90 L 540 50 L 750 50 L 770 30 L 790 70 L 810 50 L 1000 50" 
        fill="none" 
        stroke="rgba(139, 92, 246, 0.15)" 
        strokeWidth="1.5"
      />
      <path 
        className="wave-pulse"
        d="M 0 50 L 200 50 L 220 20 L 240 80 L 260 50 L 450 50 L 470 10 L 510 90 L 540 50 L 750 50 L 770 30 L 790 70 L 810 50 L 1000 50" 
        fill="none" 
        stroke="var(--accent-purple)" 
        strokeWidth="2"
      />
    </svg>
    
    {/* Secondary Fast Data Line */}
    <svg className="tech-wave-svg wave-2" viewBox="0 0 1000 100" preserveAspectRatio="none">
       <path 
        className="wave-track"
        d="M 0 50 L 1000 50" 
        fill="none" 
        stroke="rgba(59, 130, 246, 0.1)" 
        strokeWidth="1"
      />
      <path 
        className="wave-pulse-fast"
        d="M 0 50 L 1000 50" 
        fill="none" 
        stroke="var(--blue-400)" 
        strokeWidth="2"
      />
    </svg>

    {/* Tertiary Slow Data Line */}
    <svg className="tech-wave-svg wave-3" viewBox="0 0 1000 100" preserveAspectRatio="none">
      <path 
        className="wave-track"
        d="M 0 50 L 150 50 L 180 80 L 210 50 L 600 50 L 630 20 L 660 50 L 1000 50" 
        fill="none" 
        stroke="rgba(34, 211, 238, 0.1)" 
        strokeWidth="1.5"
      />
      <path 
        className="wave-pulse-slow"
        d="M 0 50 L 150 50 L 180 80 L 210 50 L 600 50 L 630 20 L 660 50 L 1000 50" 
        fill="none" 
        stroke="var(--cyan-400)" 
        strokeWidth="2"
      />
    </svg>
  </div>
);

// ── Feature Card Data ──
const sideFeatures = [
  { icon: <ShieldCheck size={20} />, title: 'Incident Resolution', color: 'teal', desc: 'AI agents triage and resolve issues faster.' },
  { icon: <Lock size={20} />, title: 'Access Management', color: 'orange', desc: 'Manage identities and permissions securely.' },
  { icon: <Activity size={20} />, title: 'Infrastructure Monitoring', color: 'blue', desc: 'Real-time insights and anomaly detection.' },
];

// ── Floating Icon Component ──
const FloatingIcon: React.FC<{ icon: React.ReactNode; className: string; delay?: number }> = ({ icon, className, delay = 0 }) => (
  <motion.div
    className={`floating-icon ${className}`}
    initial={{ opacity: 0, scale: 0 }}
    animate={{ opacity: 1, scale: 1 }}
    transition={{ duration: 0.6, delay: 1.2 + delay, ease }}
  >
    {icon}
  </motion.div>
);

// ── Feature Card Data ──
export const LandingPage: React.FC<LandingPageProps> = ({ onGoToLogin }) => {
  return (
    <div className="landing-page">
      {/* Background Effects */}
      <div className="landing-backgrounds">
        <div className="bg-gradient-orb orb-1" />
        <div className="bg-gradient-orb orb-2" />
        <div className="bg-gradient-orb orb-3" />
        <div className="bg-grid-pattern" />
        <TechWaveBackground />
      </div>

      {/* ── Navigation ── */}
      <motion.nav
        className="landing-nav"
        initial="hidden"
        animate="visible"
        variants={fadeDown}
        transition={{ duration: 0.7, ease }}
      >
        <div className="landing-nav-brand">
          <img src="/logo.png" alt="ZuuSwarm AI Operations" />
          <span>ZuuSwarm AI Operations</span>
        </div>

        <div className="landing-nav-links">
          <a href="#home" className="nav-active" onClick={(e) => {
            e.preventDefault();
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
            Home
          </a>
          <a href="#features" onClick={(e) => {
            e.preventDefault();
            document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' });
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
            Features
          </a>
          <a href="#use-cases" onClick={(e) => {
            e.preventDefault();
            document.getElementById('use-cases')?.scrollIntoView({ behavior: 'smooth' });
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
            Use Cases
          </a>
          <a href="#about" onClick={(e) => {
            e.preventDefault();
            document.getElementById('about')?.scrollIntoView({ behavior: 'smooth' });
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            About
          </a>
        </div>

        <motion.button
          className="landing-nav-cta"
          onClick={onGoToLogin}
          type="button"
          whileHover={{ scale: 1.05, boxShadow: '0 0 30px rgba(139, 92, 246, 0.3)' }}
          whileTap={{ scale: 0.97 }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          Sign In
        </motion.button>
      </motion.nav>

      {/* ── Hero Section ── */}
      <section className="landing-hero">
        
        {/* ── Floating Background Badges ── */}
        <div className="hero-floating-badges">
          <motion.div 
            className="floating-badge badge-left-1"
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.5, ease }}
          >
            <span className="fb-dot green" />
            L1 Triage: Online
          </motion.div>

          <motion.div 
            className="floating-badge badge-left-2"
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.7, ease }}
          >
            <span className="fb-icon"><Activity size={16} /></span>
            <div className="fb-text">
              <span>Server Load</span>
              <strong>24.5%</strong>
            </div>
          </motion.div>

          <motion.div 
            className="floating-badge badge-right-1"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.6, ease }}
          >
            <span className="fb-dot blue" />
            Analyzing Logs...
          </motion.div>

          <motion.div 
            className="floating-badge badge-right-2"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.8, delay: 0.8, ease }}
          >
            <span className="fb-icon"><ShieldCheck size={16} /></span>
            <div className="fb-text">
              <span>Threat Blocked</span>
              <strong>IP: 192.168.*</strong>
            </div>
          </motion.div>
        </div>

        {/* Badge */}
        <motion.div
          className="hero-badge"
          initial="hidden"
          animate="visible"
          variants={fadeUp}
          transition={{ duration: 0.6, delay: 0.3, ease }}
        >
          <span className="hero-badge-sparkle"><Sparkles size={16} /></span>
          Autonomous IT Operations, Powered by AI
        </motion.div>

        {/* Main Heading */}
        <motion.h1
          initial="hidden"
          animate="visible"
          variants={fadeUp}
          transition={{ duration: 0.8, delay: 0.5, ease }}
        >
          Your AI Assistant For{' '}
          <span className="hero-gradient-text">IT Operations</span>
        </motion.h1>

        {/* Subtitle */}
        <motion.p
          className="hero-subtitle"
          initial="hidden"
          animate="visible"
          variants={fadeUp}
          transition={{ duration: 0.8, delay: 0.7, ease }}
        >
          Resolve incidents, manage access, and monitor infrastructure health —
          all through a conversational AI swarm that thinks, investigates, and acts.
        </motion.p>

        {/* CTA Buttons */}
        <motion.div
          className="hero-actions"
          initial="hidden"
          animate="visible"
          variants={fadeUp}
          transition={{ duration: 0.8, delay: 0.9, ease }}
        >
          <button className="hero-btn-primary" onClick={onGoToLogin} type="button">
            Get Started Free
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
            </svg>
          </button>
          <button className="hero-btn-secondary" type="button">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/>
            </svg>
            Explore Demo
          </button>
        </motion.div>

        {/* ── Hero 3-Column Showcase ── */}
        <div className="hero-showcase">
          {/* Left Column: Feature Cards */}
          <motion.div
            className="hero-left-cards"
            initial="hidden"
            animate="visible"
            variants={staggerContainer}
          >
            {sideFeatures.map((feat, i) => (
              <motion.div
                key={i}
                className="side-feature-card"
                variants={fadeLeft}
                transition={{ duration: 0.7, delay: 1 + i * 0.15, ease }}
              >
                <div className="side-feature-content">
                  <div className={`side-feature-icon ${feat.color}`}>{feat.icon}</div>
                  <div className="side-feature-text">
                    <h4>{feat.title}</h4>
                    <p>{feat.desc}</p>
                  </div>
                </div>
              </motion.div>
            ))}
          </motion.div>

          {/* Center: AI Orb */}
          <motion.div
            className="hero-center-orb"
            initial="hidden"
            animate="visible"
            variants={scaleReveal}
            transition={{ duration: 1.2, delay: 0.8, ease }}
          >
            <div className="orb-glow" />
            <div className="orb-ring ring-outer">
              <div className="orbit-dot dot-1" />
              <div className="orbit-dot dot-2" />
            </div>
            <div className="orb-ring ring-inner" />
            <div className="orb-core">
              <div className="orb-eyes">
                <div className="orb-eye" />
                <div className="orb-eye" />
              </div>
              <div className="orb-mouth">
                <div className="orb-mouth-bar" />
                <div className="orb-mouth-bar" />
                <div className="orb-mouth-bar" />
                <div className="orb-mouth-bar" />
                <div className="orb-mouth-bar" />
              </div>
            </div>

            {/* Floating icons around orb */}
            <FloatingIcon icon={<Lock size={24} />} className="fi-lock" delay={0} />
            <FloatingIcon icon={<Activity size={24} />} className="fi-chart" delay={0.15} />
            <FloatingIcon icon={<ShieldCheck size={24} />} className="fi-shield" delay={0.3} />
            <FloatingIcon icon={<ClipboardCheck size={24} />} className="fi-clipboard" delay={0.45} />
          </motion.div>

          {/* Right Column: Stats Dashboard */}
          <motion.div
            className="hero-right-stats"
            initial="hidden"
            animate="visible"
            variants={fadeRight}
            transition={{ duration: 0.8, delay: 1, ease }}
          >
            <div className="stats-panel">
              <div className="stats-header">
                <span className="stats-status-dot" />
                <div>
                  <span className="stats-title">System Status</span>
                  <span className="stats-subtitle">All Systems Operational</span>
                </div>
              </div>

              <div className="stats-row">
                <div className="stats-icon orange"><Bot size={28} /></div>
                <div className="stats-info">
                  <span className="stats-label">Active Agents</span>
                  <span className="stats-value">24</span>
                  <span className="stats-meta">AI agents running</span>
                </div>
              </div>

              <div className="stats-row">
                <div className="stats-icon teal"><ShieldCheck size={28} /></div>
                <div className="stats-info">
                  <span className="stats-label">Resolved Today</span>
                  <span className="stats-value">156</span>
                  <span className="stats-meta">Incidents resolved</span>
                </div>
              </div>

              <div className="stats-row">
                <div className="stats-icon blue"><TrendingUp size={28} /></div>
                <div className="stats-info">
                  <span className="stats-label">Uptime</span>
                  <span className="stats-value">99.98%</span>
                  <span className="stats-meta">Last 30 days</span>
                </div>
              </div>
            </div>
          </motion.div>
        </div>

        {/* ── AI Terminal Preview ── */}
        <motion.div
          className="hero-terminal-section"
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-50px" }}
          variants={fadeUp}
          transition={{ duration: 1, delay: 0.2, ease }}
        >
          <div className="terminal-grid">
            <div className="terminal-window">
              <div className="terminal-titlebar">
                <div className="terminal-dots">
                  <span className="td red" />
                  <span className="td yellow" />
                  <span className="td green" />
                </div>
                <span className="terminal-tab">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2a10 10 0 110 20 10 10 0 010-20z"/><path d="M2 12h20"/></svg>
                  AI Assistant
                  <span className="terminal-online-dot" />
                </span>
              </div>
              <div className="terminal-body">
                <div className="terminal-line">
                  <span className="t-prompt">&gt;</span>
                  <span className="t-text">Deploying fix for memory leak in worker node...</span>
                </div>
                <div className="terminal-line">
                  <span className="t-check">✓</span>
                  <span className="t-text t-green">Analyzing system metrics</span>
                </div>
                <div className="terminal-line">
                  <span className="t-check">✓</span>
                  <span className="t-text t-green">Identified memory leak in service-42</span>
                </div>
                <div className="terminal-line">
                  <span className="t-check">✓</span>
                  <span className="t-text t-green">Applying patch and restarting service</span>
                </div>
                <div className="terminal-line">
                  <span className="t-check">✓</span>
                  <span className="t-text t-green">Monitoring results</span>
                </div>
                <div className="terminal-line">
                  <span className="t-prompt">$</span>
                  <span className="t-cursor" />
                </div>
              </div>
            </div>

            <div className="confidence-card premium-card">
              <div className="confidence-glow-bg" />
              <div className="confidence-header">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--purple-400)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                <span className="confidence-label">CONFIDENCE SCORE</span>
              </div>
              
              <div className="confidence-value-wrapper">
                <span className="confidence-value">98<span className="percent-sign">%</span></span>
              </div>
              
              <div className="confidence-status">
                <span className="status-dot green pulse"></span>
                <span>High Confidence</span>
              </div>
              
              <div className="confidence-bar-wrapper">
                <div className="confidence-bar">
                  <div className="confidence-fill">
                    <div className="confidence-flare" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </section>

      {/* ── Use Cases ── */}
      <motion.section
        className="landing-use-cases"
        id="use-cases"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.1 }}
      >
        <motion.h2 variants={fadeUp} transition={{ duration: 0.7, ease }}>
          Top <span>Use Cases</span>
        </motion.h2>
        <motion.div className="steps-grid" variants={staggerContainer}>
          {[
            { num: '1', icon: <Search size={24} />, title: 'Report or Detect', desc: 'An employee reports an issue via chat or voice, or the system auto-detects an anomaly.' },
            { num: '2', icon: <Bot size={24} />, title: 'AI Investigates', desc: 'The multi-agent swarm triages, investigates root cause, and determines the best remediation path.' },
            { num: '3', icon: <Zap size={24} />, title: 'Auto-Remediate', desc: 'L3 executes the fix from approved runbooks, restores the service, and logs everything automatically.' },
          ].map((step) => (
            <motion.div
              key={step.num}
              className="step-card"
              variants={cardVariant}
              transition={{ duration: 0.65, ease }}
            >
              <div className="step-number">{step.num}</div>
              <span className="step-icon">{step.icon}</span>
              <h3>{step.title}</h3>
              <p>{step.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </motion.section>

      {/* ── Features Grid ── */}
      <motion.section
        className="landing-features"
        id="features"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.1 }}
      >
        <motion.div className="landing-features-title" variants={fadeUp} transition={{ duration: 0.7, ease }}>
          <h2>Powerful <span>Features</span></h2>
        </motion.div>

        <motion.div className="features-grid-container" variants={staggerContainer}>
          {[
          { icon: <Bot size={28} />, color: 'purple', title: 'AI Chat Assistant', desc: 'Natural language interface for IT operations. Ask questions, report issues, and get instant help.' },
          { icon: <Search size={28} />, color: 'blue', title: 'Intelligent Triage', desc: 'Automatically classify incidents by type and severity, routing them to the right investigation layer.' },
          { icon: <Wrench size={28} />, color: 'cyan', title: 'Autonomous Remediation', desc: 'L2 investigates root causes and L3 applies fixes from runbooks — all without human intervention.' },
          { icon: <Mic size={28} />, color: 'purple', title: 'Voice Operations', desc: 'Talk to the AI via LiveKit voice calls for hands-free incident management and status updates.' },
          { icon: <BarChart3 size={28} />, color: 'blue', title: 'Real-time Dashboards', desc: 'Monitor system health, ticket queues, and agent activity with live, auto-refreshing dashboards.' },
          { icon: <Fingerprint size={28} />, color: 'cyan', title: 'Access Management', desc: 'Handle access requests, role changes, and permission audits through secure conversational workflows.' },
        ].map((feature, i) => (
          <motion.div
            key={i}
            className="feature-card"
            variants={cardVariant}
            transition={{ duration: 0.6, ease }}
          >
            <div className={`feature-icon-box ${feature.color}`}>
              {feature.icon}
            </div>
            <h3>{feature.title}</h3>
            <p>{feature.desc}</p>
          </motion.div>
        ))}
        </motion.div>
      </motion.section>

      {/* ── About Section ── */}
      <motion.section
        className="landing-about"
        id="about"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
        variants={fadeUp}
        transition={{ duration: 0.9, ease }}
      >
        <h2>About <span>ZuuSwarm AI</span></h2>
        <p>
          ZuuSwarm is a next-generation AI ecosystem designed specifically for modern IT operations.
          Rather than relying on disjointed scripts and manual runbooks, ZuuSwarm acts as an
          intelligent, autonomous layer over your infrastructure. It continuously monitors health,
          investigates anomalies via its multi-agent architecture (L1 Triage, L2 Investigation, L3 Remediation),
          and interacts seamlessly with engineering teams through real-time voice calls and chat.
        </p>
      </motion.section>

      {/* ── Footer ── */}
      <motion.footer
        className="landing-footer"
        initial={{ opacity: 0, y: 20 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, ease }}
      >
        <div className="footer-content">
          <div className="footer-brand">
            <img src="/logo.png" alt="ZuuSwarm AI Operations" />
            <span>ZuuSwarm AI Operations</span>
          </div>

          <div className="footer-links">
            <a href="#home" onClick={(e) => {
              e.preventDefault();
              window.scrollTo({ top: 0, behavior: 'smooth' });
            }}>Home</a>
            <a href="#features" onClick={(e) => {
              e.preventDefault();
              document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' });
            }}>Features</a>
            <a href="#about" onClick={(e) => {
              e.preventDefault();
              document.getElementById('about')?.scrollIntoView({ behavior: 'smooth' });
            }}>About</a>
          </div>

          <hr className="footer-divider" />

          <p className="footer-copy">
            © 2026 ZuuSwarm AI — Built for modern IT teams. All rights reserved.
          </p>
        </div>
      </motion.footer>
    </div>
  );
};
