/* @ds-bundle: {"format":4,"namespace":"McLender","components":[{"name":"Button"},{"name":"StatusPill"},{"name":"Money"},{"name":"StatTile"},{"name":"Field"},{"name":"DataTable"},{"name":"LoanStepper"},{"name":"AssessmentCard"}]} */
(function () {
  var React = window.React, h = React.createElement;
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(" "); }

  /* Money: kina with two decimals, tabular figures */
  function formatKina(amount, opts) {
    opts = opts || {};
    var n = Number(amount);
    if (!isFinite(n)) return "-";
    var s = Math.abs(n).toLocaleString("en-AU", { minimumFractionDigits: opts.decimals == null ? 2 : opts.decimals, maximumFractionDigits: opts.decimals == null ? 2 : opts.decimals });
    return (n < 0 ? "-" : "") + (opts.currency === false ? "" : "K ") + s;
  }
  function Money(p) {
    return h("span", { className: cx("ml-money", p.size && "ml-money-" + p.size, p.tone && "ml-tone-" + p.tone, p.className) },
      formatKina(p.amount, { decimals: p.decimals }));
  }

  function Button(p) {
    var rest = Object.assign({}, p); delete rest.variant; delete rest.size; delete rest.className;
    return h("button", Object.assign({ type: "button" }, rest, {
      className: cx("ml-btn", "ml-btn-" + (p.variant || "secondary"), p.size === "sm" && "ml-btn-sm", p.className)
    }), p.children);
  }

  var STATUS = {
    DRAFT: ["Draft", "neutral"], PENDING: ["Pending approval", "info"], APPROVED: ["Approved", "brand"],
    REJECTED: ["Rejected", "danger"], ACTIVE: ["Active", "success"], ARREARS: ["In arrears", "warning"],
    ARREARS_LATE: ["In arrears", "danger"], CLOSED: ["Closed", "neutral"], WRITTEN_OFF: ["Written off", "danger"],
    PAID: ["Paid", "success"], DUE: ["Due", "gold"], OVERDUE: ["Overdue", "danger"],
    APPROVE: ["Approve", "success"], REFER: ["Refer", "warning"], DECLINE: ["Decline", "danger"]
  };
  function StatusPill(p) {
    var s = STATUS[p.status] || [p.status, "neutral"];
    var label = p.label || (p.days ? s[0] + " · " + p.days + " days" : s[0]);
    return h("span", { className: "ml-pill ml-pill-" + (p.tone || s[1]) }, h("span", { className: "ml-pill-dot", "aria-hidden": "true" }), label);
  }

  function StatTile(p) {
    return h("div", { className: cx("ml-stat", p.emphasis && "ml-stat-" + p.emphasis) },
      h("div", { className: "ml-stat-label" }, p.label),
      h("div", { className: "ml-stat-value" }, p.value),
      p.delta ? h("div", { className: "ml-stat-delta ml-tone-" + (p.deltaTone || "muted") }, p.delta) : null,
      p.hint ? h("div", { className: "ml-stat-hint" }, p.hint) : null);
  }

  var fid = 0;
  function Field(p) {
    var ref = React.useRef(null); if (!ref.current) ref.current = p.id || "ml-f-" + (++fid);
    var id = ref.current, hintId = id + "-hint";
    var input = p.children || h("input", {
      id: id, className: "ml-input", type: p.type || "text", inputMode: p.inputMode, placeholder: p.placeholder,
      defaultValue: p.defaultValue, "aria-invalid": p.error ? "true" : undefined, "aria-describedby": (p.hint || p.error) ? hintId : undefined
    });
    return h("div", { className: cx("ml-field", p.error && "ml-field-error") },
      h("label", { className: "ml-label", htmlFor: id }, p.label, p.optional ? h("span", { className: "ml-optional" }, " optional") : null),
      p.prefix ? h("div", { className: "ml-affix" }, h("span", { className: "ml-prefix" }, p.prefix), input) : input,
      (p.error || p.hint) ? h("div", { id: hintId, className: p.error ? "ml-error" : "ml-hint" }, p.error || p.hint) : null);
  }

  function DataTable(p) {
    return h("div", { className: "ml-table-wrap" },
      h("table", { className: "ml-table" },
        p.caption ? h("caption", null, p.caption) : null,
        h("thead", null, h("tr", null, p.columns.map(function (c) {
          return h("th", { key: c.key, scope: "col", className: c.align === "right" ? "ml-right" : null }, c.label);
        }))),
        h("tbody", null, p.rows.map(function (r, i) {
          return h("tr", { key: r.id || i, className: p.selectedId != null && r.id === p.selectedId ? "ml-selected" : null, onClick: p.onRowClick ? function () { p.onRowClick(r); } : undefined },
            p.columns.map(function (c) {
              var v = c.render ? c.render(r) : r[c.key];
              return h("td", { key: c.key, className: c.align === "right" ? "ml-right" : null }, v);
            }));
        }))));
  }

  var STEPS = ["Submitted", "Assessed", "Approved", "Disbursed", "Repaying", "Closed"];
  function LoanStepper(p) {
    var cur = p.current || 0;
    return h("ol", { className: "ml-steps", "aria-label": "Loan progress" }, (p.steps || STEPS).map(function (s, i) {
      var state = i < cur ? "done" : i === cur ? "current" : "todo";
      return h("li", { key: s, className: "ml-step ml-step-" + state, "aria-current": state === "current" ? "step" : undefined },
        h("span", { className: "ml-step-mark", "aria-hidden": "true" }, state === "done" ? "✓" : String(i + 1)), h("span", null, s));
    }));
  }

  function AssessmentCard(p) {
    var dti = Number(p.dti || 0), max = Number(p.maxDti || 0.4);
    var pct = Math.min(dti / (max * 1.5), 1) * 100, limitPct = (1 / 1.5) * 100;
    return h("section", { className: "ml-card ml-assess", "aria-label": "Affordability assessment" },
      h("header", { className: "ml-assess-head" },
        h("div", null, h("div", { className: "ml-eyebrow" }, "Affordability check"), h("div", { className: "ml-assess-score" }, p.score, h("span", null, " / 100 risk score"))),
        h(StatusPill, { status: p.recommendation })),
      h("div", { className: "ml-meter-label" }, h("span", null, "Debt-to-income"), h("strong", null, (dti * 100).toFixed(1) + "%"), h("span", { className: "ml-muted" }, "limit " + (max * 100).toFixed(0) + "%")),
      h("div", { className: "ml-meter", role: "img", "aria-label": "Debt-to-income " + (dti * 100).toFixed(1) + "% against a limit of " + (max * 100).toFixed(0) + "%" },
        h("div", { className: "ml-meter-fill ml-meter-" + (dti > max ? (dti > max + 0.05 ? "danger" : "warning") : "success"), style: { width: pct + "%" } }),
        h("div", { className: "ml-meter-limit", style: { left: limitPct + "%" } })),
      h("dl", { className: "ml-assess-facts" },
        h("div", null, h("dt", null, "Monthly payment"), h("dd", null, h(Money, { amount: p.monthlyPayment }))),
        h("div", null, h("dt", null, "Most we can lend"), h("dd", null, h(Money, { amount: p.cap })))),
      p.notes && p.notes.length ? h("ul", { className: "ml-assess-notes" }, p.notes.map(function (n, i) { return h("li", { key: i }, n); })) : null);
  }

  window.McLender = Object.assign(window.McLender || {}, {
    Button: Button, StatusPill: StatusPill, Money: Money, StatTile: StatTile, Field: Field,
    DataTable: DataTable, LoanStepper: LoanStepper, AssessmentCard: AssessmentCard, formatKina: formatKina
  });
})();
