import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      'node_modules/**',
      'reports/**',
      'test-results/**',
      'playwright-report/**',
      'python-unit/**',
      'legacy-manual/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Typed linting, scoped to TypeScript sources: `no-floating-promises` is
    // the rule that matters most in a Playwright suite (a missing `await` on
    // an assertion makes a test pass unconditionally), and it needs type
    // information — which the flat-config file itself is not part of.
    files: ['**/*.ts'],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      // Test code reads better with explicit awaits than with returned promises.
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'error',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
  {
    // The framework's own logger is the one place console output is the point.
    files: ['src/core/logger.ts'],
    rules: { 'no-console': 'off' },
  },
);
