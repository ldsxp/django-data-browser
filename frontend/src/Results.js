import React from "react";
import "./App.css";
import { TLink, SLink, Overlay } from "./Util";

function Spacer(props) {
  const { spaces } = props;
  if (spaces > 0) {
    return [...Array(spaces)].map((_, key) => (
      <td className="Empty" key={key} />
    ));
  }
  return null;
}

function HeadCell(props) {
  const { query, field, className } = props;
  const modelField = query.getField(field.path);
  const type = query.getType(modelField);
  return (
    <th {...{ className }}>
      <SLink onClick={() => query.removeField(field)}>close</SLink>
      {modelField.canPivot && (
        <>
          <SLink onClick={() => query.togglePivot(field)}>
            {field.pivoted ? "call_received" : "call_made"}
          </SLink>
        </>
      )}
      {modelField.concrete && type.defaultLookup ? (
        <>
          <SLink onClick={() => query.addFilter(field.path, field.prettyPath)}>
            filter_alt
          </SLink>{" "}
          <TLink onClick={() => query.toggleSort(field)}>
            {field.prettyPath.join(" ")}
            {
              {
                dsc: `↑${field.priority}`,
                asc: `↓${field.priority}`,
                null: "",
              }[field.sort]
            }
          </TLink>
        </>
      ) : (
        " " + field.prettyPath.join(" ")
      )}
    </th>
  );
}

const DataCell = React.memo((props) => {
  const { modelField, className, span, value } = props;
  let formattedValue;
  if (value === undefined) {
    formattedValue = "";
  } else if (modelField.type === "html" && value) {
    formattedValue = <div dangerouslySetInnerHTML={{ __html: value }} />;
  } else {
    formattedValue = String(value);
  }
  return (
    <td className={modelField.type + " " + className || ""} colSpan={span || 1}>
      {formattedValue}
    </td>
  );
});

function VTableHeadRow(props) {
  const { fields, query, classNameFirst, className } = props;
  return fields.map((field, i) => (
    <HeadCell
      {...{ query, field }}
      key={field.pathStr}
      className={`HoriBorder ${className} ` + (i ? "" : classNameFirst)}
    />
  ));
}

function VTableBodyRow(props) {
  const { fields, query, classNameFirst, className, row } = props;
  return fields.map((field, i) => (
    <DataCell
      key={field.pathStr}
      value={row ? row[field.pathStr] : ""}
      className={`${i ? "" : classNameFirst} ${className}`}
      modelField={query.getField(field.path)}
    />
  ));
}

function HTableRow(props) {
  const { query, field, data, span, className } = props;
  return (
    <>
      <HeadCell {...{ query, field }} />
      {data.map((col, key) => (
        <DataCell
          {...{ key, span, className }}
          value={col[field.pathStr]}
          modelField={query.getField(field.path)}
        />
      ))}
    </>
  );
}

function Results(props) {
  const { query, cols, rows, body, overlay } = props;
  return (
    <div className="Results">
      <Overlay message={overlay} />
      <div className="Scroller">
        <table>
          <thead>
            {/* pivoted data */}
            {query.colFields().map((field) => {
              return (
                <tr key={field.pathStr}>
                  <Spacer spaces={query.rowFields().length - 1} />
                  <HTableRow
                    {...{ query, field }}
                    span={query.resFields().length}
                    data={cols}
                    className={overlay && "Fade"}
                  />
                </tr>
              );
            })}

            {/* column headers */}
            <tr>
              <Spacer spaces={1 - query.rowFields().length} />
              <VTableHeadRow
                {...{ query }}
                fields={query.rowFields()}
                className="Freeze"
              />
              {cols.map((_, key) => (
                <VTableHeadRow
                  {...{ key, query }}
                  fields={query.resFields()}
                  classNameFirst="LeftBorder"
                  className="Freeze"
                />
              ))}
            </tr>
          </thead>

          {/* row headers and body */}
          <tbody className={overlay && "Fade"}>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <Spacer spaces={1 - query.rowFields().length} />
                <VTableBodyRow {...{ query, row }} fields={query.rowFields()} />
                {body.map((table, key) => (
                  <VTableBodyRow
                    {...{ key, query }}
                    fields={query.resFields()}
                    row={table[rowIndex]}
                    classNameFirst="LeftBorder"
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export { Results };
