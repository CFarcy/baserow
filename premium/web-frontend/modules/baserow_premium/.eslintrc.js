// Please keep in sync with the non premium eslintrc.js
module.exports = {
  root: true,
  env: {
    browser: true,
    node: true,
    jest: true,
    // required as jest uses jasmine's fail method
    // https://stackoverflow.com/questions/64413927/jest-eslint-fail-is-not-defined
    jasmine: true,
  },
  parserOptions: {
    parser: 'babel-eslint',
  },
  extends: [
    '@nuxtjs',
    'plugin:nuxt/recommended',
    'plugin:prettier/recommended',
    'prettier',
  ],
  plugins: ['prettier'],
  rules: {
    'no-console': 0,
    'vue/no-mutating-props': 0,
    'prettier/prettier': [
      'error',
      {
        singleQuote: true,
        semi: false,
      },
    ],
    'import/order': 'off',
  },
}
