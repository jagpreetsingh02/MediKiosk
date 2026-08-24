import { useState, useEffect, useRef } from 'react';
import { CircleUserRound, Menu, X } from 'lucide-react';
import './App.css';

export default function App() {
  const [menuOpen, setMenuOpen] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (video) {
      video.muted = true;
      video.play().catch((err) => {
        console.log("Autoplay was blocked or failed:", err);
      });
    }
  }, []);

  const navLinks = [
    { name: 'Home', href: '#home', active: true },
    { name: 'Our Approach', href: '#approach', active: false },
    { name: 'Healing Methods', href: '#methods', active: false },
  ];

  const avatars = [
    'https://images.pexels.com/photos/774909/pexels-photo-774909.jpeg?auto=compress&cs=tinysrgb&w=100',
    'https://images.pexels.com/photos/1222271/pexels-photo-1222271.jpeg?auto=compress&cs=tinysrgb&w=100',
    'https://images.pexels.com/photos/1239291/pexels-photo-1239291.jpeg?auto=compress&cs=tinysrgb&w=100',
    'https://images.pexels.com/photos/697509/pexels-photo-697509.jpeg?auto=compress&cs=tinysrgb&w=100',
  ];

  return (
    <div className="relative w-full h-screen overflow-hidden bg-black text-white select-none flex flex-col font-sans">
      {/* Background Video */}
      <video
        ref={videoRef}
        autoPlay
        loop
        muted
        playsInline
        className="absolute inset-0 w-full h-full object-cover z-0 pointer-events-none"
        src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260715_082433_69699cf8-444b-4484-93cc-053e57896dfd.mp4"
      />

      {/* Navigation (z-20, top) */}
      <nav className="relative z-20 flex items-center justify-between w-full px-5 pt-6 sm:px-8 sm:pt-8 md:px-16 lg:px-20">
        {/* Left: Custom SVG Logo */}
        <a href="#home" className="flex items-center" aria-label="Vibrant Wellness Home">
          <svg
            className="w-8 h-8 md:w-9 md:h-9 fill-white"
            viewBox="0 0 256 256"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path d="M 128 128 C 198.692 128 256 185.308 256 256 L 151.883 256 C 149.812 220.307 120.213 192 84 192 C 47.787 192 18.188 220.307 16.117 256 L 0 256 C 0 185.308 57.308 128 128 128 Z M 104.117 0 C 106.188 35.694 135.787 64 172 64 C 208.213 64 237.812 35.694 239.883 0 L 256 0 C 256 70.692 198.692 128 128 128 C 57.308 128 0 70.692 0 0 Z" />
          </svg>
          <span className="ml-3 font-semibold text-lg tracking-tight hidden sm:inline">Vibrant Wellness</span>
        </a>

        {/* Center: Desktop Navigation links (hidden on mobile) */}
        <div className="hidden md:flex items-center rounded-full px-8 py-3 liquid-glass gap-8">
          {navLinks.map((link) => (
            <a
              key={link.name}
              href={link.href}
              className={`text-sm font-medium transition-colors ${
                link.active ? 'text-white' : 'text-white/70 hover:text-white'
              }`}
            >
              {link.name}
            </a>
          ))}
        </div>

        {/* Right (Desktop): Profile Button */}
        <div className="hidden md:flex items-center">
          <button
            className="w-10 h-10 rounded-full flex items-center justify-center liquid-glass"
            aria-label="User Account"
          >
            <CircleUserRound className="w-5 h-5 text-white/80" strokeWidth={1.5} />
          </button>
        </div>

        {/* Right (Mobile): Hamburger Trigger */}
        <div className="md:hidden flex items-center">
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="relative w-10 h-10 rounded-full flex items-center justify-center liquid-glass z-50 focus:outline-none"
            aria-expanded={menuOpen}
            aria-label="Toggle navigation menu"
          >
            {/* Animated Icon Swap */}
            <div className="relative w-5 h-5">
              <Menu
                className={`absolute inset-0 w-5 h-5 text-white transition-all duration-300 transform ${
                  menuOpen ? 'rotate-90 scale-0 opacity-0' : 'rotate-0 scale-100 opacity-100'
                }`}
              />
              <X
                className={`absolute inset-0 w-5 h-5 text-white transition-all duration-300 transform ${
                  menuOpen ? 'rotate-0 scale-100 opacity-100' : '-rotate-90 scale-0 opacity-0'
                }`}
              />
            </div>
          </button>
        </div>
      </nav>

      {/* Mobile Menu Overlay (z-40 overlay, md:hidden) */}
      <div
        className={`fixed inset-0 z-40 bg-black/80 backdrop-blur-xl flex flex-col items-center justify-center md:hidden transition-all duration-500 ${
          menuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
      >
        <div
          className={`flex flex-col items-center gap-8 transition-transform duration-500 ${
            menuOpen ? 'translate-y-0' : '-translate-y-8'
          }`}
        >
          {navLinks.map((link) => (
            <a
              key={`mob-${link.name}`}
              href={link.href}
              onClick={() => setMenuOpen(false)}
              className="text-2xl font-medium text-white hover:text-white/80 transition-colors"
            >
              {link.name}
            </a>
          ))}
          <div className="flex items-center gap-3 mt-6">
            <div className="w-10 h-10 rounded-full flex items-center justify-center liquid-glass">
              <CircleUserRound className="w-5 h-5 text-white/80" strokeWidth={1.5} />
            </div>
            <span className="text-sm font-light text-white/60">Account</span>
          </div>
        </div>
      </div>

      {/* Main Content (z-10) */}
      <main
        className={`relative z-10 flex-grow flex flex-col justify-between px-5 pb-8 pt-4 sm:px-8 sm:pb-10 md:px-16 md:pb-14 lg:px-20 lg:pb-16 transition-opacity duration-300 ${
          menuOpen ? 'opacity-0 pointer-events-none md:opacity-100 md:pointer-events-auto' : 'opacity-100'
        }`}
      >
        {/* Top Block */}
        <div className="mt-14 sm:mt-20 md:mt-28 max-w-2xl flex flex-col items-start">
          {/* Badge Pill */}
          <div className="inline-flex items-center gap-2.5 sm:gap-3 rounded-full px-3 py-1.5 sm:px-4 sm:py-2 mb-5 sm:mb-6 liquid-glass">
            {/* Overlapping Avatars */}
            <div className="flex -space-x-2">
              {avatars.map((url, i) => (
                <img
                  key={`avatar-${i}`}
                  src={url}
                  alt={`Wellness member ${i + 1}`}
                  className="h-5 w-5 sm:h-6 sm:w-6 rounded-full border-2 border-white/20 object-cover"
                />
              ))}
            </div>
            <span className="text-xs sm:text-sm font-light text-white/80">
              our path to natural wellness
            </span>
          </div>

          {/* Heading */}
          <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-normal leading-[1.05] text-white tracking-[-0.05em]">
            Heal Your Body
            <br />
            Naturally
          </h1>

          {/* Subtitle */}
          <p className="mt-4 sm:mt-5 text-sm sm:text-base md:text-lg font-light text-white/70">
            Holistic wellness. Transformative results.
          </p>

          {/* CTA Button */}
          <button className="liquid-glass rounded-full px-6 py-3 sm:px-7 sm:py-3.5 mt-6 sm:mt-8 text-sm font-medium text-white transition duration-300 hover:bg-white/10 focus:outline-none">
            Begin Your Journey
          </button>
        </div>

        {/* Bottom Stats */}
        <div className="flex items-end gap-6 sm:gap-10 md:gap-16 mt-8">
          {/* Column 1 */}
          <div className="flex flex-col items-start gap-1">
            {/* Dot Pattern Icon */}
            <div className="relative w-5 h-5 mb-1" aria-hidden="true">
              {/* Row 1 (top, 1 dot) */}
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '3px', left: '8.75px' }}
              />
              {/* Row 2 (middle, 3 dots) */}
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '9px', left: '4.75px' }}
              />
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '9px', left: '8.75px' }}
              />
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '9px', left: '12.75px' }}
              />
              {/* Row 3 (bottom, 5 dots) */}
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '15px', left: '0.75px' }}
              />
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '15px', left: '4.75px' }}
              />
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '15px', left: '8.75px' }}
              />
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '15px', left: '12.75px' }}
              />
              <div
                className="absolute w-[2.5px] h-[2.5px] bg-white/60"
                style={{ top: '15px', left: '16.75px' }}
              />
            </div>
            <span className="text-xl sm:text-2xl md:text-3xl font-normal text-white leading-none">
              48 Hours
            </span>
            <span className="text-xs sm:text-sm font-light text-white/60">
              Initial Consultation
            </span>
          </div>

          {/* Column 2 */}
          <div className="flex flex-col items-start gap-1">
            {/* 3x3 Grid Icon */}
            <div className="grid grid-cols-3 gap-[2px] w-5 h-5 mb-1" aria-hidden="true">
              {/* Row 1 */}
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-white/60" />
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-transparent" />
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-white/60" />
              {/* Row 2 */}
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-transparent" />
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-white/60" />
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-transparent" />
              {/* Row 3 */}
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-white/60" />
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-transparent" />
              <div className="w-[5px] h-[5px] rounded-[1.5px] bg-white/60" />
            </div>
            <span className="text-xl sm:text-2xl md:text-3xl font-normal text-white leading-none">
              12 Sessions
            </span>
            <span className="text-xs sm:text-sm font-light text-white/60">
              Healing Sessions
            </span>
          </div>
        </div>
      </main>
    </div>
  );
}
