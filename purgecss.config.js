module.exports = {
  content: [
    'app/templates/**/*.html',
    'app/static/js/app.js',
  ],
  css: ['app/static/vendor/tailwind.min.css'],
  output: 'app/static/vendor/',
  safelist: [
    'hidden',
    'hover:opacity-70',
    'hover:opacity-80',
    'hover:underline',
    'hover:bg-red-700',
    'lg:flex-row',
    'lg:w-5/12',
    'lg:w-7/12',
  ],
};
