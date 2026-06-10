const analysisElement = document.getElementById("analysis-data");
const analysis = analysisElement ? JSON.parse(analysisElement.textContent) : null;

function makeChart(id, type, labels, values, label, colors) {
  const element = document.getElementById(id);
  if (!element) return;

  new Chart(element, {
    type,
    data: {
      labels,
      datasets: [
        {
          label,
          data: values,
          backgroundColor: colors,
          borderColor: "#ffffff",
          borderWidth: 1
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: type === "doughnut",
          position: "bottom"
        }
      },
      scales: type === "doughnut" ? {} : {
        y: {
          beginAtZero: true
        }
      }
    }
  });
}

if (analysis) {
  makeChart(
    "sameGenreYearChart",
    "bar",
    analysis.sameGenreYears.labels,
    analysis.sameGenreYears.values,
    analysis.sameGenreYears.label,
    ["#2f5f98", "#0f766e", "#cc3f2f", "#8a6f2a", "#5b6472"]
  );

  makeChart(
    "sameYearGenreChart",
    "doughnut",
    analysis.sameYearGenres.labels,
    analysis.sameYearGenres.values,
    analysis.sameYearGenres.label,
    ["#cc3f2f", "#0f766e", "#2f5f98", "#8a6f2a", "#59636f", "#d88a2d"]
  );
}
