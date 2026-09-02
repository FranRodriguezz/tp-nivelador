package client

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/7574-sistemas-distribuidos/tp-nivelador/src/logger"
	"github.com/7574-sistemas-distribuidos/tp-nivelador/src/protocol"
)

const CONNECTION_ATTEMPTS_MAX = 15
const CONNECTION_ATTEMPS_DELAY_MS = 500


type ClientConfig struct {
	ServerHost string
	ServerPort string
	AgencyId   string
	InputFile  string
	OutputFile string
}

type Client struct {
	conn   net.Conn
	config ClientConfig
}

func NewClient(config ClientConfig) (*Client, error) {
	conn, err := connectToServer(config.ServerHost, config.ServerPort)
	if err != nil {
		logger.Warn("connect-to-server", logger.Fail)
		return nil, err
	}

	client := &Client{conn: conn, config: config}
	return client, nil
}

func connectToServer(host, port string) (net.Conn, error) {
	const action = "connect-to-server"
	var err error
	var conn net.Conn

	logger.Info(action, logger.InProgress)
	for i := range CONNECTION_ATTEMPTS_MAX {
		conn, err = net.Dial("tcp", host+":"+port)
		if err != nil {
			logger.Warn(action, logger.Fail, "attempt", i)
			time.Sleep(CONNECTION_ATTEMPS_DELAY_MS * time.Millisecond)
			continue
		}

		logger.Info(action, logger.Success)
		break
	}

	return conn, err
}

func (client *Client) Run() error {
	defer client.conn.Close()

	inFile, err := os.Open(client.config.InputFile)
	if err != nil {
		logger.Error("open-input-file", logger.Fail)
		return err
	}
	defer inFile.Close()

	outFile, err := os.Create(client.config.OutputFile)
	if err != nil {
		logger.Error("create-output-file", logger.Fail)
		return err
	}
	defer outFile.Close()

	scanner := bufio.NewScanner(inFile)
	for scanner.Scan() {
		line := scanner.Text()
		parsedLine, err := parseBet(line, client.config.AgencyId)
		if err != nil {
			logger.Error("parse-bet", logger.Fail, "line", line)
			return err
		}

		codifiedBet := protocol.EncodeBet(parsedLine)

		err = protocol.SendMessage(client.conn, protocol.BET, codifiedBet)
		if err != nil {
			logger.Error("send-bet", logger.Fail, "line", line)
			return err
		}
	}

	if err := scanner.Err(); err != nil {
		logger.Error("read-input-file", logger.Fail)
		return err
	}

	if err := protocol.SendMessage(client.conn, protocol.DONE, nil); err != nil {
		logger.Error("send-done", logger.Fail)
		return err
	}

	_, payload, err := protocol.RecvMessage(client.conn)
	if err != nil {
		logger.Error("recv-winners", logger.Fail)
		return err
	}

	winners, err := protocol.DecodeWinners(payload)
	if err != nil {
		logger.Error("decode-winners", logger.Fail)
		return err
	}

	for _, winner := range winners {
		if _, err := outFile.WriteString(fmt.Sprintf("%d\n", winner)); err != nil {
			logger.Error("write-winner", logger.Fail, "winner", winner)
			return err
		}
	}
	logger.Info("process-bets", logger.Success, "agency-id", client.config.AgencyId)
	return nil
}

// parseBet parses a line from the input file and returns a Bet struct.
func parseBet(line string, agencyId string) (protocol.Bet, error) {
	parts := strings.Split(line, ",")

	agencyIdInt, err := strconv.Atoi(agencyId)
	if err != nil {
		return protocol.Bet{}, err
	}

	document, err := strconv.Atoi(parts[2])
	if err != nil {
		return protocol.Bet{}, err
	}

	number, err := strconv.Atoi(parts[4])
	if err != nil {
		return protocol.Bet{}, err
	}

	return protocol.Bet{
		AgencyId:  agencyIdInt,
		FirstName: parts[0],
		LastName:  parts[1],
		Document:  document,
		Birthdate: parts[3],
		Number:    number,
	}, nil
}