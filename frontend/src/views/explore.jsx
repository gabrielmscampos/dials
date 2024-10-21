import React, { useState, useEffect } from 'react'

import Row from 'react-bootstrap/Row'
import Col from 'react-bootstrap/Col'
import Card from 'react-bootstrap/Card'
import Form from 'react-bootstrap/Form'
import Button from 'react-bootstrap/Button'
import Plot from 'react-plotly.js'

import API from '../services/api'

function linspace (start, stop, num) {
  const step = (stop - start) / (num - 1)
  return Array.from({ length: num }, (_, i) => start + step * i)
}

const createPlot = (
  meDict,
  figTitle,
  width,
  height,
  refDict = null,
  axLabels = null
) => {
  // Check if all MEs are 1D
  const all1D = Object.values(meDict).every((meInfo) => meInfo.me_id <= 95)
  if (!all1D && refDict !== null) {
    throw new Error(
      'Reference data given for invalid ME type(s). Plot 2D reference MEs separately.'
    )
  }

  // Getting info about data
  const numMes = Object.keys(meDict).length
  const numLss = meDict[Object.keys(meDict)[0]].data.length
  const numRows = Math.ceil((numMes + 1) / 2)
  const numCols = numMes > 1 ? 2 : 1
  const mes = Object.keys(meDict)

  // Create the traces for each ME
  const traces = []
  mes.forEach((me, i) => {
    const row = Math.floor(i / numCols) + 1
    const col = (i % numCols) + 1
    for (let ls = 0; ls < numLss; ls++) {
      let trace
      if (meDict[me].me_id <= 95) {
        trace = {
          type: 'bar',
          x: meDict[me].x_bins,
          y: meDict[me].data[ls],
          name: me,
          visible: ls === 0,
          xaxis: `x${col}`,
          yaxis: `y${row}`,
        }
      } else if (meDict[me].me_id >= 96) {
        trace = {
          type: 'heatmap',
          x: meDict[me].x_bins,
          y: meDict[me].y_bins,
          z: meDict[me].data[ls],
          name: me,
          visible: ls === 0,
          xaxis: `x${col}`,
          yaxis: `y${row}`,
        }
      }
      traces.push(trace)
    }
  })

  // Create slider steps
  const steps = []
  for (let i = 0; i < numLss; i++) {
    const step = {
      method: 'restyle',
      args: [{ visible: Array(numMes * numLss).fill(false) }],
      label: `LS ${i + 1}`,
    }
    for (let j = 0; j < numMes; j++) {
      step.args[0].visible[i + j * numLss] = true
    }
    steps.push(step)
  }

  // Add sliders to layout
  const layout = {
    title: { text: figTitle, font: { size: 24 } },
    sliders: [
      {
        active: 0,
        currentvalue: { prefix: 'LS: ' },
        pad: { t: 50 },
        steps,
      },
    ],
    showlegend: false,
    width,
    height,
    grid: { rows: numRows, columns: numCols, pattern: 'independent' },
  }

  // Update axes, add reference traces and adjust layout
  mes.forEach((me, i) => {
    const row = Math.floor(i / numCols) + 1
    const col = (i % numCols) + 1

    const maxData = Math.max(...meDict[me].data.flat())

    if (meDict[me].me_id <= 95) {
      layout[`yaxis${row}`] = { range: [0, maxData] }
    }

    if (meDict[me].me_id >= 96) {
      traces.forEach((trace) => {
        if (trace.type === 'heatmap') {
          trace.showscale = false
        }
      })
    }

    if (axLabels !== null) {
      layout[`xaxis${col}`] = { title: axLabels[i].x }
      layout[`yaxis${row}`] = { title: axLabels[i].y }
    }

    if (refDict !== null) {
      const traceRef = {
        type: 'scatter',
        x: refDict[me].x_bins,
        y: refDict[me].data[0],
        name: `${me}-Reference`,
        opacity: 0.6,
        line: { shape: 'hv' },
        xaxis: `x${col}`,
        yaxis: `y${row}`,
      }
      traces.push(traceRef)
    }
  })

  // Return the full data and layout
  return { data: traces, layout }
}

const PlotComponent = ({
  meDict,
  figTitle,
  width,
  height,
  refDict,
  axLabels,
}) => {
  const { data, layout } = createPlot(
    meDict,
    figTitle,
    width,
    height,
    refDict,
    axLabels
  )

  return <Plot data={data} layout={layout} config={{ responsive: true }} />
}

const Explore = () => {
  const [runNumber, setRunNumber] = useState()
  const [monitoringElement, setMonitoringElement] = useState()
  const [meDim, setMEDim] = useState()
  const [data, setData] = useState()
  const [normData, setNormData] = useState()
  const [datasetName, setDatasetName] = useState()
  const [primaryDatasetName, setPrimaryDatasetName] = useState()
  const [isLoading, setLoading] = useState(true)

  const handleSubmit = () => {
    setLoading(true)
    API.histogram
      .list({
        dim: meDim,
        me: monitoringElement,
        datasetRegex: datasetName,
        runNumber,
      })
      .then((response) => {
        const dataMe = response.results.map((item) => item.data)
        const entriesMe = response.results.map((item) => item.entries)
        const meId = response.results[0].me_id
        const xBins = linspace(
          response.results[0].x_min,
          response.results[0].x_max,
          response.results[0].x_bin
        )
        let yBins = []
        if (meId >= 96) {
          yBins = linspace(
            response.results[0].y_min,
            response.results[0].y_max,
            response.results[0].y_bin
          )
        }
        const result = {
          [monitoringElement]: {
            data: dataMe,
            entries: entriesMe,
            me_id: meId,
            x_bins: xBins,
            y_bins: yBins,
          },
        }
        setPrimaryDatasetName(response.results[0].dataset.split('/')[1])
        setData(result)
      })
      .finally(() => {
        setLoading(false)
      })
  }

  useEffect(() => {
    if (
      runNumber !== undefined &&
      primaryDatasetName !== undefined &&
      data !== undefined
    ) {
      API.oms
        .datasetrates({
          runNumber,
          datasetName: primaryDatasetName,
        })
        .then((response) => {
          const rates = response.data.map((item) => item.attributes.rate)
          const res = data[monitoringElement].data.map((outerArray, index) => {
            return outerArray.map((innerArray) => {
              return innerArray.map((value) => {
                return value / rates[index]
              })
            })
          })
          const result = {
            [monitoringElement]: {
              data: res,
              entries: data[monitoringElement].entries,
              me_id: data[monitoringElement].me_id,
              x_bins: data[monitoringElement].x_bins,
              y_bins: data[monitoringElement].y_bins,
            },
          }
          setNormData(result)
        })
    }
  }, [data, runNumber, primaryDatasetName, monitoringElement])

  return (
    <Row className='mt-5 mb-3 m-3'>
      <Col sm={3}>
        <Card>
          <Card.Header className='text-center' as='h4'>
            Filters
          </Card.Header>
          <Card.Body>
            <Form.Group className='mb-3' controlId='formRunNumber'>
              <Form.Label>Run number</Form.Label>
              <Form.Control
                type='number'
                value={runNumber}
                onChange={(e) => setRunNumber(e.target.value)}
                placeholder='Enter the run number'
              />
            </Form.Group>
            <Form.Group className='mb-3' controlId='formDim'>
              <Form.Label>Dimension</Form.Label>
              <Form.Control
                type='number'
                value={meDim}
                onChange={(e) => setMEDim(e.target.value)}
                placeholder='Enter the ME dimension'
              />
            </Form.Group>
            <Form.Group className='mb-3' controlId='formMe'>
              <Form.Label>ME</Form.Label>
              <Form.Control
                type='string'
                value={monitoringElement}
                onChange={(e) => setMonitoringElement(e.target.value)}
              />
            </Form.Group>
            <Form.Group className='mb-3' controlId='formDatasetName'>
              <Form.Label>Dataset Name</Form.Label>
              <Form.Control
                type='string'
                value={datasetName}
                onChange={(e) => setDatasetName(e.target.value)}
                placeholder='Enter the dataset name'
              />
            </Form.Group>
            <Button variant='primary' type='submit' onClick={handleSubmit}>
              Submit
            </Button>
          </Card.Body>
        </Card>
      </Col>
      <Col sm={9}>
        <Card className='text-center'>
          <Card.Header as='h4'>Files</Card.Header>
          <Card.Body>
            <Row>
              <Col md={6}>
                {isLoading !== true && (
                  <PlotComponent
                    meDict={data}
                    figTitle='My Plot'
                    hspace={0.1}
                    vspace={0.1}
                    width={800}
                    height={600}
                  />
                )}
              </Col>
              <Col md={6}>
                {normData !== undefined && (
                  <PlotComponent
                    meDict={normData}
                    figTitle='My Plot'
                    hspace={0.1}
                    vspace={0.1}
                    width={800}
                    height={600}
                  />
                )}
              </Col>
            </Row>
          </Card.Body>
        </Card>
      </Col>
    </Row>
  )
}

export default Explore
