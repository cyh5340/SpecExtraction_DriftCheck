function truncate(str, n) {
  return str.length <= n ? str : str.slice(0, n) + "...";
}

module.exports = { truncate };
