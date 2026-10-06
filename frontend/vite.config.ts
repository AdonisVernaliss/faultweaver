import adapter from '@sveltejs/adapter-node';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [sveltekit({ adapter: adapter(), csp: { mode: 'auto', directives: {
    'default-src': ['self'], 'script-src': ['self'], 'style-src': ['self', 'unsafe-inline'],
    'img-src': ['self', 'data:'], 'connect-src': ['self'], 'frame-src': ['self'],
    'frame-ancestors': ['none'], 'object-src': ['none'], 'base-uri': ['self'], 'form-action': ['self']
  } } })],
  test: {
    include: ['src/**/*.test.ts']
  }
});
