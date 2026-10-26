export const THEME_STORAGE_KEY = "theme"
export const THEME_COLORS = { dark: "#0A0A0A", light: "#FAFAFA" } as const

/**
 * Runs before paint (inlined in <head>) so the stored theme applies without a
 * flash. Dark is the default. Also marks the document as JS-enabled for the
 * GSAP reveal styles in globals.css.
 */
export const themeScript = `(function(){try{var d=document.documentElement;d.classList.add('js');var t=localStorage.getItem('${THEME_STORAGE_KEY}')||'dark';d.classList.toggle('dark',t==='dark');var m=document.querySelector('meta[name="theme-color"]');if(m)m.setAttribute('content',t==='dark'?'${THEME_COLORS.dark}':'${THEME_COLORS.light}')}catch(e){}})()`
