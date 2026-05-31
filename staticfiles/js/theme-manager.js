/**
 * Theme Manager - Handles dark theme persistence and activation
 * TUV-Compliant Dark Theme Controller
 */

class ThemeManager {
    constructor() {
        this.STORAGE_KEY = 'tuv-theme-preference';
        this.DARK_THEME = 'dark';
        this.LIGHT_THEME = 'light';
        this.DEFAULT_THEME = this.DARK_THEME; // Set dark as default
        this.init();
    }

    /**
     * Initialize theme on page load
     */
    init() {
        // Load saved preference or use default
        const savedTheme = this.getSavedTheme();
        const prefersDark = this.getSystemPreference();
        const themeToApply = savedTheme || this.DEFAULT_THEME;
        
        // Apply theme immediately to prevent flash
        this.applyTheme(themeToApply);
        
        // Setup theme toggle if button exists
        this.setupToggleButton();
    }

    /**
     * Get saved theme preference from localStorage
     */
    getSavedTheme() {
        return localStorage.getItem(this.STORAGE_KEY);
    }

    /**
     * Get system color scheme preference
     */
    getSystemPreference() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches
            ? this.DARK_THEME
            : this.LIGHT_THEME;
    }

    /**
     * Apply theme to document
     */
    applyTheme(theme) {
        const isDark = theme === this.DARK_THEME;
        
        // Apply to body
        document.body.classList.toggle('dark-theme', isDark);
        document.body.classList.toggle('light-theme', !isDark);
        
        // Apply to html element for attribute selectors
        document.documentElement.setAttribute('data-theme', theme);
        
        // Save preference
        localStorage.setItem(this.STORAGE_KEY, theme);
        
        // Update meta theme-color for mobile browsers
        this.updateMetaThemeColor(isDark);
        
        // Dispatch custom event for other scripts
        window.dispatchEvent(new CustomEvent('themechange', { detail: { theme } }));
    }

    /**
     * Update meta theme-color tag for mobile browsers
     */
    updateMetaThemeColor(isDark) {
        let metaThemeColor = document.querySelector('meta[name="theme-color"]');
        
        if (!metaThemeColor) {
            metaThemeColor = document.createElement('meta');
            metaThemeColor.name = 'theme-color';
            document.head.appendChild(metaThemeColor);
        }
        
        // Set appropriate color for dark/light theme
        metaThemeColor.content = isDark ? '#0d1117' : '#ffffff';
    }

    /**
     * Toggle between dark and light themes
     */
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || this.DEFAULT_THEME;
        const newTheme = currentTheme === this.DARK_THEME ? this.LIGHT_THEME : this.DARK_THEME;
        this.applyTheme(newTheme);
        return newTheme;
    }

    /**
     * Get current theme
     */
    getCurrentTheme() {
        return document.documentElement.getAttribute('data-theme') || this.DEFAULT_THEME;
    }

    /**
     * Setup theme toggle button
     */
    setupToggleButton() {
        const toggleBtn = document.getElementById('theme-toggle-btn');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                const newTheme = this.toggleTheme();
                this.updateToggleButtonState();
            });
            
            // Set initial state
            this.updateToggleButtonState();
        }
    }

    /**
     * Update toggle button visual state
     */
    updateToggleButtonState() {
        const toggleBtn = document.getElementById('theme-toggle-btn');
        if (!toggleBtn) return;
        
        const isDark = this.getCurrentTheme() === this.DARK_THEME;
        toggleBtn.textContent = isDark ? '☀️ Light' : '🌙 Dark';
        toggleBtn.setAttribute('aria-pressed', isDark);
        toggleBtn.setAttribute('title', isDark ? 'Switch to Light Theme' : 'Switch to Dark Theme');
    }

    /**
     * Respond to system theme changes
     */
    watchSystemPreference() {
        const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
        darkModeQuery.addEventListener('change', (e) => {
            // Only change if user hasn't explicitly set a preference
            if (!this.getSavedTheme()) {
                this.applyTheme(e.matches ? this.DARK_THEME : this.LIGHT_THEME);
                this.updateToggleButtonState();
            }
        });
    }
}

// Initialize theme manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
        window.themeManager.watchSystemPreference();
    });
} else {
    window.themeManager = new ThemeManager();
    window.themeManager.watchSystemPreference();
}

// Expose theme functions globally for inline scripts
window.toggleTheme = () => {
    if (window.themeManager) {
        return window.themeManager.toggleTheme();
    }
};

window.setTheme = (theme) => {
    if (window.themeManager) {
        window.themeManager.applyTheme(theme);
    }
};

window.getTheme = () => {
    if (window.themeManager) {
        return window.themeManager.getCurrentTheme();
    }
};
